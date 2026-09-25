import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import PlacementStubPage from "./PlacementStubPage";
import { unavailablePlacementSession } from "./placementSession";

describe("PlacementStubPage", () => {
  it("renders the honest unavailable state without assessment data", () => {
    render(<PlacementStubPage live={false} />);

    expect(screen.getByRole("heading", { name: "入門測驗" })).toBeInTheDocument();
    expect(screen.getByText("Placement Test")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Placement test not available" })).toBeInTheDocument();
    expect(screen.getByText("Not available")).toBeInTheDocument();
    expect(screen.getByText("入門測驗目前未開放。")).toBeInTheDocument();
    expect(screen.queryByText(/timer|progress|HSK|TOCFL|score|question/i)).not.toBeInTheDocument();
  });

  it("keeps the default adapter at the unavailable contract boundary", () => {
    expect(unavailablePlacementSession()).toEqual({ status: "unavailable" });
  });
});
