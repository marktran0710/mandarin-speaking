import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import StudentButton from "./StudentButton";
import StudentSystemText from "./StudentSystemText";

describe("StudentButton bilingual hint", () => {
  it("combines multiple control labels into one pinyin and English tooltip", () => {
    render(
      <StudentButton variant="primary">
        <StudentSystemText k="start" withinControl />{" "}
        <StudentSystemText k="useIt" withinControl />
      </StudentButton>,
    );

    const button = screen.getByRole("button");
    expect(button.querySelectorAll('[role="tooltip"]')).toHaveLength(1);
    expect(button.querySelector(".sa-button__tooltip-pinyin")).toHaveTextContent("Kāishǐ Yùnyòng");
    expect(button.querySelector(".sa-button__tooltip-en")).toHaveTextContent("Start · Use it");
    expect(button.querySelectorAll(".sa-system-text[title]")).toHaveLength(0);
  });
});
