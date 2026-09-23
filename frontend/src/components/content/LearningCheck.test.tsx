import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { getResearchProbesDue, postResearchProbeResponse } = vi.hoisted(() => ({
  getResearchProbesDue: vi.fn(),
  postResearchProbeResponse: vi.fn(),
}));

vi.mock("../../services/api/vocabulary-research", () => ({
  getResearchProbesDue,
  postResearchProbeResponse,
}));

import LearningCheck from "./LearningCheck";

describe("LearningCheck", () => {
  beforeEach(() => {
    getResearchProbesDue.mockReset();
    postResearchProbeResponse.mockReset();
  });

  it("calls onDone immediately when there are no due questions", async () => {
    getResearchProbesDue.mockResolvedValue({ questions: [] });
    const onDone = vi.fn();

    render(<LearningCheck onDone={onDone} />);

    await waitFor(() => expect(onDone).toHaveBeenCalled());
  });

  it("walks through every due question and never shows correctness feedback", async () => {
    getResearchProbesDue.mockResolvedValue({
      questions: [
        { assignmentId: 1, wordId: "word-a", questionType: "mc_translation", prompt: "What does word-a mean?", choices: ["A", "B"] },
        { assignmentId: 2, wordId: "word-b", questionType: "mc_translation", prompt: "What does word-b mean?", choices: ["C", "D"] },
      ],
    });
    postResearchProbeResponse.mockResolvedValue({ accepted: true });
    const onDone = vi.fn();

    render(<LearningCheck onDone={onDone} />);

    await screen.findByText("What does word-a mean?");
    fireEvent.click(screen.getByText("A"));
    fireEvent.click(screen.getByRole("button", { name: /Next/i }));

    await screen.findByText("What does word-b mean?");
    expect(screen.queryByText(/correct/i)).not.toBeInTheDocument();
    fireEvent.click(screen.getByText("D"));
    fireEvent.click(screen.getByRole("button", { name: /Finish/i }));

    await screen.findByText("Check complete");
    expect(postResearchProbeResponse).toHaveBeenCalledWith(1, "A", expect.stringContaining("1"));
    expect(postResearchProbeResponse).toHaveBeenCalledWith(2, "D", expect.stringContaining("2"));
    expect(screen.queryByText(/correct/i)).not.toBeInTheDocument();
    expect(onDone).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: /Continue/i }));
    expect(onDone).toHaveBeenCalled();
  });
});
