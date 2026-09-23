import { describe, expect, it } from "vitest";
import {
  blankConversationExchange,
  emptyCustomStoryDraft,
  validateCustomStoryDraft,
} from "./StoryBuilderSection.helpers";

const baseDraft = {
  ...emptyCustomStoryDraft,
  title: "Conversation story",
};

describe("validateCustomStoryDraft - conversation practice (Epic 3)", () => {
  it("is unaffected when conversation practice is disabled", () => {
    const errors = validateCustomStoryDraft(
      { ...baseDraft, conversationEnabled: false, conversationExchanges: [] },
      [],
      null,
    );
    expect(errors.form).toBeUndefined();
  });

  it("rejects an enabled toggle with zero exchanges", () => {
    const errors = validateCustomStoryDraft(
      { ...baseDraft, conversationEnabled: true, conversationExchanges: [] },
      [],
      null,
    );
    expect(errors.form).toMatch(/at least one conversation exchange/i);
  });

  it("rejects an exchange missing the character's line", () => {
    const exchange = { ...blankConversationExchange("ex-1"), studentText: "你好！", characterAudioUrl: "/a.wav" };
    const errors = validateCustomStoryDraft(
      { ...baseDraft, conversationEnabled: true, conversationExchanges: [exchange] },
      [],
      null,
    );
    expect(errors.form).toMatch(/Exchange 1/);
  });

  it("rejects an exchange missing the student's target response", () => {
    const exchange = { ...blankConversationExchange("ex-1"), characterText: "你好", characterAudioUrl: "/a.wav" };
    const errors = validateCustomStoryDraft(
      { ...baseDraft, conversationEnabled: true, conversationExchanges: [exchange] },
      [],
      null,
    );
    expect(errors.form).toMatch(/Exchange 1/);
  });

  it("rejects an otherwise-complete exchange missing character audio", () => {
    const exchange = { ...blankConversationExchange("ex-1"), characterText: "你好", studentText: "你好！" };
    const errors = validateCustomStoryDraft(
      { ...baseDraft, conversationEnabled: true, conversationExchanges: [exchange] },
      [],
      null,
    );
    expect(errors.form).toMatch(/character audio/i);
  });

  it("identifies the specific incomplete exchange when others are complete", () => {
    const complete = { ...blankConversationExchange("ex-1"), characterText: "你好", studentText: "你好！", characterAudioUrl: "/a.wav" };
    const incomplete = { ...blankConversationExchange("ex-2"), characterText: "再見" };
    const errors = validateCustomStoryDraft(
      { ...baseDraft, conversationEnabled: true, conversationExchanges: [complete, incomplete] },
      [],
      null,
    );
    expect(errors.form).toMatch(/Exchange 2/);
  });

  it("passes with every exchange complete", () => {
    const complete = { ...blankConversationExchange("ex-1"), characterText: "你好", studentText: "你好！", characterAudioUrl: "/a.wav" };
    const errors = validateCustomStoryDraft(
      { ...baseDraft, conversationEnabled: true, conversationExchanges: [complete] },
      [],
      null,
    );
    expect(errors.form).toBeUndefined();
  });
});
