import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import App from "./App";

// The three initial student-data fetches (audio records, published topics,
// help requests) used to each paint their own screen the instant they
// resolved, so a returning student's workspace visibly assembled itself
// piece by piece on a slow connection. App.tsx now gates every student
// route behind all three settling once — this file proves that gate
// actually blocks, and actually releases, instead of trusting the wiring.
vi.mock("./shared/api/learningApi", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./shared/api/learningApi")>();
  return {
    ...actual,
    canUseDatabase: () => true,
    listCustomStories: vi.fn(async () => []),
    listHelpRequests: vi.fn(async () => []),
  };
});

function signInAsStudent() {
  localStorage.setItem(
    "studentSession",
    JSON.stringify({
      role: "student",
      name: "Ada",
      signedInAt: "2026-01-01T00:00:00.000Z",
    }),
  );
}

describe("App — student data must be ready before a student route renders", () => {
  it("shows the loading gate, not the workspace, while a fetch is still pending, then releases it once all three settle", async () => {
    const api = await import("./shared/api/learningApi");
    let resolveAudio!: (value: never[]) => void;
    const audioPromise = new Promise<never[]>((resolve) => {
      resolveAudio = resolve;
    });
    vi.spyOn(api, "listAudioRecords").mockReturnValue(audioPromise);

    signInAsStudent();
    render(<App />);

    expect(
      screen.getByRole("heading", { name: /Loading your progress/ }),
    ).toBeInTheDocument();
    // The whole student route (rail included) is behind the gate, so while
    // it is loading the rail must not be on screen at all.
    expect(
      screen.queryByRole("navigation", { name: "Learning areas" }),
    ).not.toBeInTheDocument();

    resolveAudio([]);

    await waitFor(() =>
      expect(
        screen.queryByRole("heading", { name: /Loading your progress/ }),
      ).not.toBeInTheDocument(),
    );
    // The workspace's left rail is the marker that the route actually
    // rendered (it replaced the old page-sized "我的學習" heading this test
    // used to look for, which no longer exists).
    expect(
      screen.getByRole("navigation", { name: "Learning areas" }),
    ).toBeInTheDocument();
  });

  it("releases the gate even when a fetch fails, instead of loading forever", async () => {
    const api = await import("./shared/api/learningApi");
    vi.spyOn(api, "listAudioRecords").mockRejectedValue(new Error("network down"));

    signInAsStudent();
    render(<App />);

    await waitFor(() =>
      expect(
        screen.queryByRole("heading", { name: /Loading your progress/ }),
      ).not.toBeInTheDocument(),
    );
    // The workspace's left rail is the marker that the route actually
    // rendered (it replaced the old page-sized "我的學習" heading this test
    // used to look for, which no longer exists).
    expect(
      screen.getByRole("navigation", { name: "Learning areas" }),
    ).toBeInTheDocument();
  });
});
