import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import App from "./App";

describe("App role flows", () => {
  it("lets a student enter the learning app with the default profile", async () => {
    const user = userEvent.setup();
    render(<App />);

    expect(
      screen.getByRole("heading", { name: "Mandarin Story Coach" }),
    ).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Student Login" }));
    expect(screen.getByRole("heading", { name: "學生登入" })).toBeInTheDocument();
    expect(screen.getByLabelText("Student name")).toHaveValue("Student Demo");

    await user.click(screen.getByRole("button", { name: "Enter Student Mode" }));

    expect(
      screen.getByRole("heading", { name: "Choose a Taiwan Story" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "My Stories" })).toBeInTheDocument();
  });

  it("opens the teacher dashboard after teacher login", async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.click(screen.getByRole("button", { name: "Teacher Login" }));
    expect(screen.getByRole("heading", { name: "教師登入" })).toBeInTheDocument();
    expect(screen.getByLabelText("Teacher name")).toHaveValue("Teacher Demo");

    await user.click(screen.getByRole("button", { name: "Enter Teacher Mode" }));

    expect(
      screen.getByRole("heading", { name: "Class Speaking Dashboard" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Submissions")).toBeInTheDocument();
    expect(screen.getByText("No submissions yet")).toBeInTheDocument();
  });

  it("lets a student open the workbook and jump to a story part recording task", async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.click(screen.getByRole("button", { name: "Student Login" }));
    await user.click(screen.getByRole("button", { name: "Enter Student Mode" }));
    await user.click(screen.getByRole("button", { name: "My Stories" }));

    expect(screen.getByRole("heading", { name: "My Story Workbook" })).toBeInTheDocument();
    expect(screen.getAllByText("Needs recording").length).toBeGreaterThan(0);

    await user.click(screen.getAllByRole("button", { name: "Record this part" })[0]);

    expect(
      screen.getByRole("heading", { name: "Taiwan Lantern Festival Story Challenge" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Story concept map" })).toBeInTheDocument();
  });

  it("persists the active role across reloads", () => {
    localStorage.setItem("activeRole", "teacher");

    render(<App />);

    const overview = screen.getByRole("region", { name: "Class overview" });
    expect(within(overview).getByText("Submissions")).toBeInTheDocument();
  });
});
