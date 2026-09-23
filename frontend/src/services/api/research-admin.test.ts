import { beforeEach, describe, expect, it, vi } from "vitest";

const { fetchWithRetry } = vi.hoisted(() => ({ fetchWithRetry: vi.fn() }));

vi.mock("./client", () => ({
  BACKEND_URL: "http://backend.test",
  fetchWithRetry,
}));

import { getResearchAdminSummary } from "./research-admin";

describe("getResearchAdminSummary", () => {
  beforeEach(() => {
    fetchWithRetry.mockReset();
  });

  it("fetches the admin summary endpoint with the study id as a query param", async () => {
    fetchWithRetry.mockResolvedValue(
      new Response(
        JSON.stringify({
          studyId: "study-1",
          name: "Pilot",
          status: "active",
          participants: { active: 5, total: 6 },
          assignmentBalance: { C: 10, B: 10, S: 10, BS: 10 },
          totalAssignments: 40,
          fidelity: {
            coreCompletedCount: 3,
            practice: { itemsSelectedByCondition: {}, bktOnCount: 2, bktOffCount: 2, sessionsCreated: 1 },
            retention: { enrolledByCondition: {}, reviewsDelivered: 0, averageDelayDays: null },
            probes: { assigned: 0, completed: 0, completionRate: null },
            policyViolations: 0,
          },
        }),
        { status: 200 },
      ),
    );

    const summary = await getResearchAdminSummary("study-1");

    expect(fetchWithRetry).toHaveBeenCalledWith(
      "http://backend.test/api/research/vocabulary/admin/summary?study_id=study-1",
      { method: "GET" },
    );
    expect(summary.studyId).toBe("study-1");
    expect(summary.participants).toEqual({ active: 5, total: 6 });
  });

  it("throws with the backend's detail message on failure", async () => {
    fetchWithRetry.mockResolvedValue(
      new Response(JSON.stringify({ detail: "No such study" }), { status: 404 }),
    );

    await expect(getResearchAdminSummary("no-such")).rejects.toThrow("No such study");
  });
});
