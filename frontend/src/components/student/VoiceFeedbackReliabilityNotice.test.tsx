import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import VoiceFeedbackReliabilityNotice from "./VoiceFeedbackReliabilityNotice";

describe("VoiceFeedbackReliabilityNotice", () => {
  it("announces when an unsafe attempt cannot be scored", () => {
    render(
      <VoiceFeedbackReliabilityNotice
        assessment={{
          level: "retry",
          canCountForProgress: false,
          reason: "too-little-audio",
        }}
      />,
    );

    expect(screen.getByRole("alert")).toHaveTextContent("Score unavailable");
    expect(screen.getByRole("alert")).toHaveTextContent("enough pitch");
    expect(screen.getByRole("alert")).not.toHaveTextContent("10–20 cm");
  });

  it.each(["reliable", "estimate"] as const)(
    "renders nothing for the %s level",
    (level) => {
      // Both used to print a paragraph of English above every result — one
      // saying the evidence looked usable, one saying the feedback was an
      // estimate. Neither told a learner anything they could act on, so the
      // component now stays silent unless the recording actually failed.
      const { container } = render(
        <VoiceFeedbackReliabilityNotice
          assessment={{
            level,
            canCountForProgress: level === "reliable",
            reason: "unverified",
          }}
          attemptCount={2}
        />,
      );
      expect(container).toBeEmptyDOMElement();
    },
  );

  it("no longer escalates to a teacher on repeated attempts", () => {
    render(
      <VoiceFeedbackReliabilityNotice
        assessment={{
          level: "retry",
          canCountForProgress: false,
          reason: "too-little-audio",
        }}
        attemptCount={5}
      />,
    );
    expect(screen.getByRole("alert")).not.toHaveTextContent("Ask a teacher");
  });
});
