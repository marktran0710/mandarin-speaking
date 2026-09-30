import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import LessonReferenceGate from "./LessonReferenceGate";

describe("LessonReferenceGate", () => {
  it("shows a loading status while the pitch data is on its way", () => {
    render(<LessonReferenceGate status="loading" onRetry={() => undefined} />);
    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it("offers a retry when loading failed", () => {
    const onRetry = vi.fn();
    render(<LessonReferenceGate status="error" onRetry={onRetry} />);
    fireEvent.click(screen.getByRole("button", { name: /重試|Chóngshì/ }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });
});
