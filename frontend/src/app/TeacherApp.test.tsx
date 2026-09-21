import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import TeacherApp from "./TeacherApp";

/** The logo is the only edge out of the teacher login screen besides "Back
 * to student site". It used to be wired to a no-op onNavigate, so clicking
 * it did nothing at all. */
describe("TeacherApp login screen", () => {
  const realLocation = window.location;

  beforeEach(() => {
    localStorage.clear();
  });

  afterEach(() => {
    Object.defineProperty(window, "location", {
      configurable: true,
      value: realLocation,
    });
  });

  it("sends the logo click to the teacher app root", async () => {
    Object.defineProperty(window, "location", {
      configurable: true,
      value: { ...realLocation, href: "" },
    });
    const user = userEvent.setup();
    render(<TeacherApp />);

    await user.click(screen.getByRole("button", { name: /慢慢中文/ }));

    expect(window.location.href).toContain("teacher.html");
  });
});
