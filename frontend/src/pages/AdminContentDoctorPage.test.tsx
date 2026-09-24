import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import AdminContentDoctorPage from "./AdminContentDoctorPage";
import { getContentInventory } from "../services/api/content-doctor";
import type { ContentDoctorReport } from "../services/api/content-doctor";

vi.mock("../services/api/content-doctor", () => ({ getContentInventory: vi.fn() }));

const baseReport: ContentDoctorReport = {
  generatedAt: "2026-09-24T00:00:00Z",
  readOnly: true,
  ownership: {},
  summary: {
    stories: 2,
    publishedStories: 1,
    canonicalWords: 15,
    quizQuestions: 45,
    mediaReferences: 8,
    mediaByDomain: {},
    mediaByStatus: {},
    orphanFiles: 1,
    findings: 2,
    findingsBySeverity: { error: 1, warning: 1 },
    findingsByCode: { missing_round_question: 1, orphan_media_file: 1 },
  },
  lessons: [
    {
      storyId: "s5-1",
      title: "我的房間",
      lessonNumber: 5,
      lessonSubOrder: 1,
      published: true,
      sources: { canonicalVocabulary: "custom_stories.vocab_assessment", speakingVocabulary: [], conversation: "custom_stories.conversation_turns" },
      counts: { frames: 6, canonicalWords: 15, quizQuestions: 45, speakingWords: 15, conversationTurns: 0, findings: 1 },
      findings: [{ code: "missing_round_question", severity: "error", storyId: "s5-1", location: "vocab_assessment", detail: { wordId: "W001", level: "hard" } }],
    },
  ],
  media: { references: [], orphanFiles: [{ url: "/uploads/audio/orphan.wav", kind: "audio", bytes: 1200, mimeType: "audio/wav" }] },
  findings: [
    { code: "missing_round_question", severity: "error", storyId: "s5-1", location: "vocab_assessment", detail: { wordId: "W001", level: "hard" } },
    { code: "orphan_media_file", severity: "warning", storyId: null, location: "/uploads/audio/orphan.wav", detail: { bytes: 1200 } },
  ],
};

beforeEach(() => {
  vi.mocked(getContentInventory).mockReset().mockResolvedValue(structuredClone(baseReport));
});

describe("AdminContentDoctorPage", () => {
  it("loads the report on mount and shows the summary counts", async () => {
    render(<AdminContentDoctorPage />);
    await screen.findByText("15");
    expect(screen.getByText("45")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
    expect(getContentInventory).toHaveBeenCalledTimes(1);
  });

  it("defaults to showing only error-severity findings", async () => {
    render(<AdminContentDoctorPage />);
    await screen.findByText("missing round question");
    expect(screen.queryByText("orphan media file")).not.toBeInTheDocument();
  });

  it("switches to warnings and shows the story-less orphan finding", async () => {
    const user = userEvent.setup();
    render(<AdminContentDoctorPage />);
    await screen.findByText("missing round question");
    await user.click(screen.getByRole("radio", { name: "Warnings" }));
    expect(screen.getByText("orphan media file")).toBeInTheDocument();
    expect(screen.queryByText("missing round question")).not.toBeInTheDocument();
  });

  it("shows every finding when All is selected", async () => {
    const user = userEvent.setup();
    render(<AdminContentDoctorPage />);
    await screen.findByText("missing round question");
    await user.click(screen.getByRole("radio", { name: "All" }));
    expect(screen.getByText("missing round question")).toBeInTheDocument();
    expect(screen.getByText("orphan media file")).toBeInTheDocument();
  });

  it("resolves a finding's storyId to its lesson title", async () => {
    render(<AdminContentDoctorPage />);
    await screen.findByText("我的房間");
  });

  it("refetches on Refresh", async () => {
    const user = userEvent.setup();
    render(<AdminContentDoctorPage />);
    await screen.findByText("missing round question");
    await user.click(screen.getByRole("button", { name: /Refresh/ }));
    await waitFor(() => expect(getContentInventory).toHaveBeenCalledTimes(2));
  });

  it("shows an error message when the report fails to load", async () => {
    vi.mocked(getContentInventory).mockReset().mockRejectedValue(new Error("Could not load the content inventory report."));
    render(<AdminContentDoctorPage />);
    await screen.findByRole("alert");
    expect(screen.getByRole("alert")).toHaveTextContent("Could not load the content inventory report.");
  });
});
