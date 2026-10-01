import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  canUseDatabase: vi.fn(() => true),
  isAdminSession: vi.fn(() => false),
  getPlacementStatus: vi.fn(),
}));

vi.mock("../../services/database", () => ({ canUseDatabase: mocks.canUseDatabase }));
vi.mock("../../utils/studentSession", () => ({ isAdminSession: mocks.isAdminSession }));
vi.mock("@shared/api/placement-test", () => ({ getPlacementStatus: mocks.getPlacementStatus }));

import { usePlacementGate } from "./usePlacementGate";

const status = (gated: boolean) => ({ configured: true, required: true, completed: !gated, gated });

describe("usePlacementGate", () => {
  beforeEach(() => {
    mocks.canUseDatabase.mockReturnValue(true);
    mocks.isAdminSession.mockReturnValue(false);
    mocks.getPlacementStatus.mockReset();
  });

  it("never gates the admin session and does not even ask the server", () => {
    mocks.isAdminSession.mockReturnValue(true);
    const { result } = renderHook(() => usePlacementGate());
    expect(result.current.state).toBe("clear");
    expect(mocks.getPlacementStatus).not.toHaveBeenCalled();
  });

  it("does not gate when there is no backend to ask", () => {
    mocks.canUseDatabase.mockReturnValue(false);
    const { result } = renderHook(() => usePlacementGate());
    expect(result.current.state).toBe("clear");
    expect(mocks.getPlacementStatus).not.toHaveBeenCalled();
  });

  it("is loading until the server answers, then required for a gated student", async () => {
    mocks.getPlacementStatus.mockResolvedValue(status(true));
    const { result } = renderHook(() => usePlacementGate());
    expect(result.current.state).toBe("loading");
    await waitFor(() => expect(result.current.state).toBe("required"));
  });

  it("is clear for a student the server does not gate", async () => {
    mocks.getPlacementStatus.mockResolvedValue(status(false));
    const { result } = renderHook(() => usePlacementGate());
    await waitFor(() => expect(result.current.state).toBe("clear"));
  });

  it("fails open when the status cannot be loaded, so a network blip never traps a student", async () => {
    mocks.getPlacementStatus.mockRejectedValue(new Error("offline"));
    const { result } = renderHook(() => usePlacementGate());
    await waitFor(() => expect(result.current.state).toBe("clear"));
  });

  it("unlocks after refresh once the server reports the test as completed", async () => {
    mocks.getPlacementStatus.mockResolvedValueOnce(status(true)).mockResolvedValueOnce(status(false));
    const { result } = renderHook(() => usePlacementGate());
    await waitFor(() => expect(result.current.state).toBe("required"));
    await act(async () => {
      await result.current.refresh();
    });
    expect(result.current.state).toBe("clear");
  });
});
