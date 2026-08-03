import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import VoiceFeedbackReliabilityNotice from "./VoiceFeedbackReliabilityNotice";

describe("VoiceFeedbackReliabilityNotice", () => {
  it("announces an unsafe attempt and gives a concrete retry action", () => {
    render(
      <VoiceFeedbackReliabilityNotice
        assessment={{
          level: "retry",
          canCountForProgress: false,
          reason: "too-little-audio",
        }}
      />,
    );

    expect(screen.getByRole("alert")).toHaveTextContent(
      "Retake before trusting this score",
    );
    expect(screen.getByRole("alert")).toHaveTextContent("10–20 cm");
  });

  it("escalates repeated uncertain feedback to a teacher", () => {
    render(
      <VoiceFeedbackReliabilityNotice
        assessment={{
          level: "estimate",
          canCountForProgress: true,
          reason: "unverified",
        }}
        attemptCount={2}
      />,
    );

    expect(screen.getByRole("status")).toHaveTextContent(
      "Ask a teacher to review",
    );
  });
});
