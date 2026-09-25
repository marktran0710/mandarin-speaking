export type PlacementSessionStatus = "unavailable" | "loading" | "ready" | "complete" | "error";

export interface PlacementSessionViewModel {
  status: PlacementSessionStatus;
}

export type PlacementSessionAdapter = () => PlacementSessionViewModel;

/**
 * Placement has no learner-facing API contract yet. Keep that boundary
 * explicit so the page cannot accidentally fabricate an assessment session.
 */
export const unavailablePlacementSession: PlacementSessionAdapter = () => ({
  status: "unavailable",
});

export function usePlacementSession(
  adapter: PlacementSessionAdapter = unavailablePlacementSession,
): PlacementSessionViewModel {
  return adapter();
}
