import { render, screen, fireEvent, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import SelfEvalStep from "./SelfEvalStep";

describe("SelfEvalStep", () => {
  it("keeps the submit button disabled until both questions are answered", () => {
    render(<SelfEvalStep onSubmit={vi.fn()} onSkip={vi.fn()} />);

    const submit = screen.getByRole("button", { name: /See system feedback/ });
    expect(submit).toBeDisabled();

    const [contentGroup] = screen.getAllByRole("radiogroup");
    fireEvent.click(within(contentGroup).getByRole("radio", { name: /Good/ }));
    expect(submit).toBeDisabled();
  });

  it("submits the selected levels once both questions are answered", () => {
    const onSubmit = vi.fn();
    render(<SelfEvalStep onSubmit={onSubmit} onSkip={vi.fn()} />);

    const [contentGroup, pronunciationGroup] = screen.getAllByRole("radiogroup");
    fireEvent.click(
      within(contentGroup).getByRole("radio", { name: /Good/ }),
    );
    fireEvent.click(
      within(pronunciationGroup).getByRole("radio", { name: /OK/ }),
    );

    const submit = screen.getByRole("button", { name: /See system feedback/ });
    expect(submit).not.toBeDisabled();
    fireEvent.click(submit);

    expect(onSubmit).toHaveBeenCalledWith({ content: "good", pronunciation: "ok" });
  });

  it("skips without requiring an answer", () => {
    const onSkip = vi.fn();
    render(<SelfEvalStep onSubmit={vi.fn()} onSkip={onSkip} />);

    fireEvent.click(screen.getByRole("button", { name: /Skip/ }));
    expect(onSkip).toHaveBeenCalled();
  });
});
