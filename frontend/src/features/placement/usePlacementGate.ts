import { useCallback, useEffect, useState } from "react";
import { getPlacementStatus } from "@shared/api/placement-test";
import { canUseDatabase } from "../../services/database";
import { isAdminSession } from "../../utils/studentSession";

export type PlacementGateState = "loading" | "required" | "clear";

/**
 * Is this student held at the placement test before the rest of Student Mode
 * opens? Only the server knows (a new account that has not yet completed an
 * attempt, while a test is published), so the answer is fetched, not stored.
 *
 * It is a UI gate like the lesson gates: the admin session is never held, and
 * when the status cannot be loaded the student is let through rather than
 * trapped behind a network error.
 */
export function usePlacementGate(): { state: PlacementGateState; refresh: () => Promise<void> } {
  const exempt = isAdminSession() || !canUseDatabase();
  const [state, setState] = useState<PlacementGateState>(exempt ? "clear" : "loading");

  const refresh = useCallback(async () => {
    if (isAdminSession() || !canUseDatabase()) {
      setState("clear");
      return;
    }
    try {
      const status = await getPlacementStatus();
      setState(status.gated ? "required" : "clear");
    } catch {
      setState("clear");
    }
  }, []);

  useEffect(() => {
    if (exempt) return;
    void refresh();
  }, [exempt, refresh]);

  return { state, refresh };
}
