import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import userEvent from "@testing-library/user-event";
import type { PlacementBlueprint, PlacementAttempt } from "@shared/api/placement-test";

const { blueprint, attempt } = vi.hoisted(() => {
  const blueprint: PlacementBlueprint = {
  configured: true,
  revision: 1,
  questionCount: 2,
  questions: [
    { questionId: "q1", sourceStoryId: "s1", sourceStoryTitle: "Daily", sourceWordId: "w1", round: 1, tier: "tier1", position: 1, questionType: "basic_meaning_mcq", answerFormat: "single_choice", targetWord: "茶", prompt: "Choose", options: ["tea", "rice"] },
    { questionId: "q2", sourceStoryId: "s1", sourceStoryTitle: "Daily", sourceWordId: "w2", round: 1, tier: "tier1", position: 2, questionType: "basic_meaning_mcq", answerFormat: "single_choice", targetWord: "水", prompt: "Choose", options: ["water", "fire"] },
  ],
  };
  const attempt: PlacementAttempt = { attemptId: "a1", revision: 1, totalQuestions: 2, questions: blueprint.questions };
  return { blueprint, attempt };
});
vi.mock("@shared/api/placement-test", async () => {
  const actual = await vi.importActual<typeof import("@shared/api/placement-test")>("@shared/api/placement-test");
  return { ...actual, getPlacementBlueprint: vi.fn().mockResolvedValue(blueprint), startPlacementAttempt: vi.fn().mockResolvedValue(attempt) };
});
import PlacementPage from "./PlacementPage";
import { unavailablePlacementSession } from "./placementSession";

describe("PlacementPage", () => {
  it("renders the honest unavailable state without assessment data", () => {
    render(<PlacementPage live={false} />);

    expect(screen.getByRole("heading", { name: "入門測驗" })).toBeInTheDocument();
    expect(screen.getAllByText("入門測驗").length).toBeGreaterThan(0);
    expect(screen.getByRole("heading", { name: "入門測驗暫時無法使用" })).toBeInTheDocument();
    expect(screen.getByText("尚未開放")).toBeInTheDocument();
    expect(screen.getByText("入門測驗目前未開放。")).toBeInTheDocument();
    expect(screen.queryByText(/timer|progress|HSK|TOCFL|score|question/i)).not.toBeInTheDocument();
  });

  it("keeps the default adapter at the unavailable contract boundary", () => {
    expect(unavailablePlacementSession()).toEqual({ status: "unavailable" });
  });

  it("keeps the question counter out of the ready state and shows it after starting", async () => {
    const user = userEvent.setup();
    render(<PlacementPage />);

    await screen.findByText("開始測驗");
    expect(screen.queryByText("第 1 / 2 題")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "開始測驗" }));
    await waitFor(() => expect(screen.getByText("第 1 / 2 題")).toBeInTheDocument());
  });
});
