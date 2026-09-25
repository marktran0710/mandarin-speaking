import { BACKEND_URL, fetchWithRetry } from "@shared/api/client";

/** Epic 8, Task 8.3/8.4: the one call the research admin page needs. Admin
 * only (backend/routers/vocab_quiz_research.py's admin/summary route) -
 * the only place in the frontend allowed to know condition labels at all. */
export interface ResearchAdminSummary {
  studyId: string;
  name: string;
  status: string;
  participants: { active: number; total: number };
  assignmentBalance: Record<string, number>;
  totalAssignments: number;
  fidelity: {
    coreCompletedCount: number;
    practice: {
      itemsSelectedByCondition: Record<string, number>;
      bktOnCount: number;
      bktOffCount: number;
      sessionsCreated: number;
    };
    retention: {
      enrolledByCondition: Record<string, number>;
      reviewsDelivered: number;
      averageDelayDays: number | null;
    };
    probes: { assigned: number; completed: number; completionRate: number | null };
    policyViolations: number;
  };
}

export async function getResearchAdminSummary(studyId: string): Promise<ResearchAdminSummary> {
  const response = await fetchWithRetry(
    `${BACKEND_URL}/api/research/vocabulary/admin/summary?study_id=${encodeURIComponent(studyId)}`,
    { method: "GET" },
  );
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || "Could not load the research admin summary.");
  }
  return response.json() as Promise<ResearchAdminSummary>;
}
