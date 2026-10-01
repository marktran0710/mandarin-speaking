import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import StudentLoginPage from "./StudentLoginPage";
import { currentRole } from "../../utils/session";

describe("StudentLoginPage", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
  });

  it("creates a student session from the dedicated login form", async () => {
    const user = userEvent.setup();
    const onLogin = vi.fn();
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            id: "student-42",
            name: "Student 42",
            createdAt: "2026-08-22T00:00:00.000Z",
            status: "active",
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      ),
    );

    render(<StudentLoginPage onLogin={onLogin} />);
    await user.type(screen.getByPlaceholderText("打上你的名字"), "Student 42");
    await user.type(screen.getByPlaceholderText("輸入教師提供的密碼"), "123456");
    await user.click(screen.getByRole("button", { name: "進入學生模式" }));

    expect(onLogin).toHaveBeenCalledOnce();
    expect(currentRole("student")).toBe("student");
    expect(JSON.parse(localStorage.getItem("studentSession") ?? "{}")).toMatchObject({
      id: "student-42",
      name: "Student 42",
      role: "student",
    });

    vi.unstubAllGlobals();
  });

  it("shows a reset-required message for a 403 with a reset-password detail", async () => {
    const user = userEvent.setup();
    const onLogin = vi.fn();
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({ detail: "Student password reset required" }),
          { status: 403, headers: { "Content-Type": "application/json" } },
        ),
      ),
    );

    render(<StudentLoginPage onLogin={onLogin} />);
    await user.type(screen.getByPlaceholderText("打上你的名字"), "Student 42");
    await user.type(screen.getByPlaceholderText("輸入教師提供的密碼"), "123456");
    await user.click(screen.getByRole("button", { name: "進入學生模式" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("這個帳號需要先重設密碼");
    expect(onLogin).not.toHaveBeenCalled();

    vi.unstubAllGlobals();
  });

  it("shows an inactive-account message for a 403 without a reset-password detail", async () => {
    const user = userEvent.setup();
    const onLogin = vi.fn();
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({ detail: "Student account is inactive" }),
          { status: 403, headers: { "Content-Type": "application/json" } },
        ),
      ),
    );

    render(<StudentLoginPage onLogin={onLogin} />);
    await user.type(screen.getByPlaceholderText("打上你的名字"), "Student 42");
    await user.type(screen.getByPlaceholderText("輸入教師提供的密碼"), "123456");
    await user.click(screen.getByRole("button", { name: "進入學生模式" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("這個帳號目前停用");
    expect(onLogin).not.toHaveBeenCalled();

    vi.unstubAllGlobals();
  });

  describe("creating an account", () => {
    const student = { id: "student-77", name: "Lan", createdAt: "2026-10-01T00:00:00.000Z", status: "active" };
    const reply = (status: number, body: unknown) =>
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }),
      );

    const openSignup = async (user: ReturnType<typeof userEvent.setup>) => {
      await user.click(screen.getByRole("button", { name: "還沒有帳號？建立帳號" }));
    };

    it("creates an account from the login page and signs the student straight in", async () => {
      const user = userEvent.setup();
      const onLogin = vi.fn();
      const fetchMock = reply(201, student);
      vi.stubGlobal("fetch", fetchMock);

      render(<StudentLoginPage onLogin={onLogin} />);
      await openSignup(user);
      expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("建立帳號");
      await user.type(screen.getByPlaceholderText("打上你的名字"), "Lan");
      await user.type(screen.getByPlaceholderText("想一個密碼"), "lan-password");
      await user.click(screen.getByRole("button", { name: "建立帳號並開始" }));

      const [url, init] = fetchMock.mock.calls[0];
      expect(String(url)).toMatch(/\/api\/students\/signup$/);
      expect(init.method).toBe("POST");
      expect(JSON.parse(init.body)).toEqual({ name: "Lan", password: "lan-password" });
      expect(onLogin).toHaveBeenCalledOnce();
      expect(JSON.parse(localStorage.getItem("studentSession") ?? "{}")).toMatchObject({
        id: "student-77", name: "Lan", role: "student",
      });
      vi.unstubAllGlobals();
    });

    it("says so when the name is already taken and does not sign in", async () => {
      const user = userEvent.setup();
      const onLogin = vi.fn();
      vi.stubGlobal("fetch", reply(409, { detail: "That name is already taken." }));

      render(<StudentLoginPage onLogin={onLogin} />);
      await openSignup(user);
      await user.type(screen.getByPlaceholderText("打上你的名字"), "Lan");
      await user.type(screen.getByPlaceholderText("想一個密碼"), "lan-password");
      await user.click(screen.getByRole("button", { name: "建立帳號並開始" }));

      expect(await screen.findByRole("alert")).toHaveTextContent("這個名字有人用了，換一個。");
      expect(onLogin).not.toHaveBeenCalled();
      expect(localStorage.getItem("studentSession")).toBeNull();
      vi.unstubAllGlobals();
    });

    it("tells a name the server refuses apart from a password it refuses", async () => {
      const user = userEvent.setup();
      vi.stubGlobal("fetch", reply(400, { detail: "That name can't be used." }));
      render(<StudentLoginPage onLogin={vi.fn()} />);
      await openSignup(user);
      await user.type(screen.getByPlaceholderText("打上你的名字"), "admin");
      await user.type(screen.getByPlaceholderText("想一個密碼"), "lan-password");
      await user.click(screen.getByRole("button", { name: "建立帳號並開始" }));
      expect(await screen.findByRole("alert")).toHaveTextContent("這個名字不能用，換一個。");
      vi.unstubAllGlobals();

      vi.stubGlobal("fetch", reply(400, { detail: "Password must be at least 6 characters." }));
      await user.click(screen.getByRole("button", { name: "建立帳號並開始" }));
      expect(await screen.findByRole("alert")).toHaveTextContent("這個密碼不能用，換一個長一點的。");
      vi.unstubAllGlobals();
    });

    it("asks the student to wait after too many tries", async () => {
      const user = userEvent.setup();
      vi.stubGlobal("fetch", reply(429, { detail: "Too many login attempts. Try again later." }));
      render(<StudentLoginPage onLogin={vi.fn()} />);
      await openSignup(user);
      await user.type(screen.getByPlaceholderText("打上你的名字"), "Lan");
      await user.type(screen.getByPlaceholderText("想一個密碼"), "lan-password");
      await user.click(screen.getByRole("button", { name: "建立帳號並開始" }));
      expect(await screen.findByRole("alert")).toHaveTextContent("試太多次了，等一下再試。");
      vi.unstubAllGlobals();
    });

    it("asks for a name and a password before calling the server", async () => {
      const user = userEvent.setup();
      const fetchMock = reply(201, student);
      vi.stubGlobal("fetch", fetchMock);
      render(<StudentLoginPage onLogin={vi.fn()} />);
      await openSignup(user);
      await user.click(screen.getByRole("button", { name: "建立帳號並開始" }));
      expect(await screen.findByRole("alert")).toHaveTextContent("請輸入名字和密碼。");
      expect(fetchMock).not.toHaveBeenCalled();
      vi.unstubAllGlobals();
    });

    it("can go back to signing in, and keeps the login form unchanged", async () => {
      const user = userEvent.setup();
      render(<StudentLoginPage onLogin={vi.fn()} />);
      await openSignup(user);
      await user.click(screen.getByRole("button", { name: "已經有帳號？登入" }));
      expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("學生登入");
      expect(screen.getByPlaceholderText("輸入教師提供的密碼")).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "進入學生模式" })).toBeInTheDocument();
    });
  });
});
