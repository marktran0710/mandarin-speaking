import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import AdminMaterialsPage from "./AdminMaterialsPage";

describe("Admin Materials bulk imports", () => {
  it("keeps audio, image, and script uploads together and opens a preview dialog", async () => {
    const user = userEvent.setup();
    render(<AdminMaterialsPage />);

    expect(screen.getByRole("heading", { name: "Upload audios", level: 3 })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Upload images", level: 3 })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Upload scripts", level: 3 })).toBeInTheDocument();
    expect(screen.getByLabelText("Upload audio files for lessons 5 to 8")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Choose images" }));
    expect(screen.getByRole("dialog", { name: "Upload images" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Download sample" })).toBeInTheDocument();
  });

  it("keeps the three upload actions visible inside Create Story Activity", async () => {
    const user = userEvent.setup();
    render(<AdminMaterialsPage />);

    await user.click(screen.getByRole("button", { name: /Story Builder/ }));

    expect(screen.getByRole("region", { name: "Material uploads" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Upload images" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Upload scripts" })).toBeInTheDocument();
    expect(screen.getByLabelText("Upload audio files for lessons 5 to 8")).toBeInTheDocument();
  });
});
