import { act, render, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";

// Every window focus re-pulls the published stories so a republished script
// reaches an open tab. When nothing changed, the student shell must keep the
// SAME `topics` array: StudentApp's effects are keyed on it, so a fresh array
// re-fired the progression + speaking-progress requests on every alt-tab.
const seenTopics = vi.hoisted(() => [] as unknown[]);

vi.mock("./student/StudentApp", () => ({
  default: ({ topics }: { topics: unknown }) => {
    seenTopics.push(topics);
    return <div>student app</div>;
  },
}));

vi.mock("../services/database", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../services/database")>();
  return {
    ...actual,
    canUseDatabase: () => true,
    listCustomStories: vi.fn(async () => []),
    listHelpRequests: vi.fn(async () => []),
  };
});

describe("App — refreshing published stories on window focus", () => {
  beforeEach(() => {
    seenTopics.length = 0;
    localStorage.clear();
    localStorage.setItem(
      "studentSession",
      JSON.stringify({ role: "student", name: "Ada", signedInAt: "2026-01-01T00:00:00.000Z" }),
    );
  });

  it("keeps the same topics array when the refreshed stories are unchanged", async () => {
    const api = await import("../services/database");
    render(<App />);
    await waitFor(() => expect(seenTopics.length).toBeGreaterThan(0));
    const initial = seenTopics[seenTopics.length - 1];
    const calls = vi.mocked(api.listCustomStories).mock.calls.length;

    await act(async () => {
      window.dispatchEvent(new Event("focus"));
    });
    await waitFor(() => expect(vi.mocked(api.listCustomStories).mock.calls.length).toBeGreaterThan(calls));

    expect(seenTopics[seenTopics.length - 1]).toBe(initial);
  });
});
