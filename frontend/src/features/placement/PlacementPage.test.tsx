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
  return {
    ...actual,
    getPlacementBlueprint: vi.fn().mockResolvedValue(blueprint),
    startPlacementAttempt: vi.fn().mockResolvedValue(attempt),
    completePlacementAttempt: vi.fn().mockResolvedValue({
      attemptId: "a1", totalQuestions: 2, correctCount: 2, percentage: 100, messageKey: "CONGRATULATIONS",
    }),
  };
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

  it("tells a new account that this test comes first, and says nothing to anyone else", async () => {
    const { unmount } = render(<PlacementPage gated />);
    expect(await screen.findByText("新帳號要先完成這個測驗。")).toBeInTheDocument();
    unmount();

    render(<PlacementPage />);
    await screen.findByText("開始測驗");
    expect(screen.queryByText("新帳號要先完成這個測驗。")).not.toBeInTheDocument();
  });

  it("reports completion once and offers a way to start learning", async () => {
    const user = userEvent.setup();
    const onCompleted = vi.fn();
    const onStartLearning = vi.fn();
    render(<PlacementPage onCompleted={onCompleted} onStartLearning={onStartLearning} />);

    await user.click(await screen.findByRole("button", { name: "開始測驗" }));
    await user.click(await screen.findByRole("button", { name: /tea/ }));
    await user.click(screen.getByRole("button", { name: "下一題" }));
    await user.click(await screen.findByRole("button", { name: /water/ }));
    await user.click(screen.getByRole("button", { name: "完成測驗" }));

    expect(await screen.findByText("入門測驗完成")).toBeInTheDocument();
    expect(onCompleted).toHaveBeenCalledOnce();
    expect(onStartLearning).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "開始學習" }));
    expect(onStartLearning).toHaveBeenCalledOnce();
  });

  it("shows no start-learning button when nobody asked for one", async () => {
    const user = userEvent.setup();
    render(<PlacementPage />);
    await user.click(await screen.findByRole("button", { name: "開始測驗" }));
    await user.click(await screen.findByRole("button", { name: /tea/ }));
    await user.click(screen.getByRole("button", { name: "下一題" }));
    await user.click(await screen.findByRole("button", { name: /water/ }));
    await user.click(screen.getByRole("button", { name: "完成測驗" }));
    expect(await screen.findByText("入門測驗完成")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "開始學習" })).not.toBeInTheDocument();
  });
});
