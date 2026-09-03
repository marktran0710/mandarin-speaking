import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

const staffDb = vi.hoisted(() => ({
  students: [
    {
      id: "student-existing",
      name: "Existing Student",
      createdAt: "2026-08-01T00:00:00.000Z",
      status: "active" as const,
    },
  ],
  teachers: [
    {
      id: "teacher-existing",
      name: "Existing Teacher",
      createdAt: "2026-08-01T00:00:00.000Z",
      status: "active" as const,
    },
  ],
}));

vi.mock("../services/database", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../services/database")>();
  return {
    ...actual,
    canUseDatabase: () => true,
    listStudents: async () => [...staffDb.students],
    listTeachers: async () => [...staffDb.teachers],
    listVocabQuizAttempts: async () => [],
    listAudioRecords: async () => [],
    getAudioRecordCount: async () => 0,
    listHelpRequests: async () => [],
    createStudent: async (name: string) => {
      const student = {
        id: `student-${staffDb.students.length + 1}`,
        name,
        createdAt: "2026-08-22T00:00:00.000Z",
        status: "active" as const,
      };
      staffDb.students.push(student);
      return student;
    },
    createTeacher: async (name: string) => {
      const teacher = {
        id: `teacher-${staffDb.teachers.length + 1}`,
        name,
        createdAt: "2026-08-22T00:00:00.000Z",
        status: "active" as const,
      };
      staffDb.teachers.push(teacher);
      return teacher;
    },
    updateStudent: async (id: string, update: { name?: string; status?: "active" | "inactive" }) => {
      const student = staffDb.students.find((row) => row.id === id)!;
      Object.assign(student, update);
      return { ...student };
    },
    updateTeacher: async (id: string, update: { name?: string; status?: "active" | "inactive" }) => {
      const teacher = staffDb.teachers.find((row) => row.id === id)!;
      Object.assign(teacher, update);
      return { ...teacher };
    },
    deleteStudent: async (id: string) => {
      staffDb.students = staffDb.students.filter((row) => row.id !== id);
    },
    deleteTeacher: async (id: string) => {
      staffDb.teachers = staffDb.teachers.filter((row) => row.id !== id);
    },
  };
});

import AdminApp from "../AdminApp";
import TeacherApp from "../TeacherApp";

describe("teacher and admin integration flows", () => {
  beforeEach(() => {
    localStorage.clear();
    localStorage.setItem("adminConsoleSession", "true");
    staffDb.students = [
      {
        id: "student-existing",
        name: "Existing Student",
        createdAt: "2026-08-01T00:00:00.000Z",
        status: "active",
      },
    ];
    staffDb.teachers = [
      {
        id: "teacher-existing",
        name: "Existing Teacher",
        createdAt: "2026-08-01T00:00:00.000Z",
        status: "active",
      },
    ];
  });

  it("lets admin create, edit, and delete student and teacher accounts", async () => {
    const user = userEvent.setup();
    vi.spyOn(window, "confirm").mockReturnValue(true);
    render(<AdminApp />);

    await waitFor(() => expect(screen.getByText("Existing Student")).toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: "Students" }));

    const studentName = screen.getByPlaceholderText("Student name");
    await user.type(studentName, "New Student");
    await user.click(screen.getByRole("button", { name: "Create account" }));
    expect(await screen.findByText("New Student")).toBeInTheDocument();

    const newStudentRow = screen.getByText("New Student").closest(".account-row");
    expect(newStudentRow).not.toBeNull();
    await user.click(within(newStudentRow as HTMLElement).getByRole("button", { name: "Edit" }));
    await user.clear(screen.getByLabelText("Name"));
    await user.type(screen.getByLabelText("Name"), "Renamed Student");
    await user.click(screen.getByRole("button", { name: "Save changes" }));
    expect(await screen.findByText("Renamed Student")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Teachers" }));
    await user.click(screen.getByRole("button", { name: "Delete" }));
    await waitFor(() => expect(screen.queryByText("Existing Teacher")).not.toBeInTheDocument());
    expect(staffDb.teachers).toHaveLength(0);
  });

  it("lets a teacher sign in and land on the help queue", async () => {
    const user = userEvent.setup();
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            id: "teacher-42",
            name: "Teacher 42",
            createdAt: "2026-08-22T00:00:00.000Z",
            status: "active",
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      ),
    );
    localStorage.removeItem("adminConsoleSession");

    render(<TeacherApp />);
    await user.clear(screen.getByPlaceholderText(/teacher name/i));
    await user.type(screen.getByPlaceholderText(/teacher name/i), "Teacher 42");
    await user.type(screen.getByLabelText(/Teacher password/i), "123456");
    await user.click(screen.getByRole("button", { name: /Enter Teacher Mode/ }));

    expect(await screen.findByRole("heading", { name: "Student Help Requests" })).toBeInTheDocument();
    expect(screen.getByText("Teacher Studio")).toBeInTheDocument();
    expect(JSON.parse(localStorage.getItem("teacherSession") ?? "{}")).toMatchObject({
      id: "teacher-42",
      role: "teacher",
    });
  });
});
