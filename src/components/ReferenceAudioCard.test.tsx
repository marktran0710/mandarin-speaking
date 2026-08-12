import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import ReferenceAudioCard from "./ReferenceAudioCard";

describe("ReferenceAudioCard", () => {
  it("renders a model player from the scene audio URL", () => {
    render(<ReferenceAudioCard audioUrl="/uploads/model.wav" sentence="你好。" />);
    expect(screen.getByLabelText("Model recording: 你好。")).toHaveAttribute(
      "src",
      "/uploads/model.wav",
    );
    expect(screen.getByText("Model")).toBeInTheDocument();
  });

  it("shows a compact unavailable state without an empty player", () => {
    render(<ReferenceAudioCard sentence="你好。" />);
    expect(screen.getByText("Audio unavailable")).toBeInTheDocument();
    expect(screen.queryByLabelText(/Model recording:/)).not.toBeInTheDocument();
  });
});
