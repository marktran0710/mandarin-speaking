import { expect, test, type Page } from "@playwright/test";

const VIEWPORTS = [
  { name: "desktop", width: 1440, height: 900, kpiColumns: 4 },
  { name: "tablet", width: 768, height: 1024, kpiColumns: 2 },
  { name: "mobile", width: 390, height: 844, kpiColumns: 1 },
] as const;

const students = [
  ...Array.from({ length: 16 }, (_, index) => ({
    id: `student-${String(index + 1).padStart(2, "0")}`,
    name: `Student ${String(index + 1).padStart(2, "0")}`,
    status: "active",
    createdAt: "2026-01-01T00:00:00Z",
  })),
  { id: "inactive-01", name: "Inactive Student", status: "inactive", createdAt: "2026-01-01T00:00:00Z" },
];

function attempt(id: string, studentId: string, mode: "tier1" | "tier2" | "tier3", correctCount: number, day: number) {
  return {
    id,
    storyId: "lesson-1",
    studentId,
    studentName: students.find((student) => student.id === studentId)?.name ?? studentId,
    mode,
    completedAt: `2026-09-${String(day).padStart(2, "0")}T08:00:00Z`,
    totalQuestions: 4,
    correctCount,
    totalTimeMs: 1000,
    questionResults: [],
  };
}

const attempts = [
  attempt("s1-r1", "student-01", "tier1", 3, 20),
  attempt("s1-r2", "student-01", "tier2", 2, 21),
  attempt("s1-r3", "student-01", "tier3", 4, 22),
  attempt("s2-r1", "student-02", "tier1", 3, 20),
  attempt("s3-r1", "student-03", "tier1", 2, 20),
  attempt("s3-r2", "student-03", "tier2", 3, 21),
  attempt("s4-r1", "student-04", "tier1", 0, 20),
];

async function mockAdminApi(page: Page) {
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/admin/roster-overview") {
      await route.fulfill({ json: { students, teachers: [], quizAttempts: attempts } });
      return;
    }
    if (path === "/api/custom-stories") {
      await route.fulfill({ json: [{ id: "lesson-1", title: "At the market", frames: [] }] });
      return;
    }
    if (path === "/api/audio-records" || path === "/api/measurement-events") {
      await route.fulfill({ json: [] });
      return;
    }
    await route.fulfill({ json: [] });
  });
}

async function openRoundScores(page: Page) {
  await mockAdminApi(page);
  await page.addInitScript(() => localStorage.setItem("adminConsoleSession", "true"));
  await page.goto("/admin.html");

  const analyticsNav = page.locator(".management-nav-item", { hasText: "Student analytics" });
  const menuToggle = page.getByRole("button", { name: "Open menu" });
  if (await menuToggle.isVisible()) await menuToggle.click();
  await analyticsNav.click();

  const studentTab = page.getByRole("tab", { name: "Student analytics" });
  await studentTab.focus();
  await page.keyboard.press("ArrowRight");
  await expect(page.getByRole("tab", { name: "Round scores" })).toHaveAttribute("aria-selected", "true");
  await expect(page.getByRole("heading", { name: "Three-round quiz scores" })).toBeVisible();
  await expect(page.getByRole("combobox", { name: "Lesson" })).toHaveValue("lesson-1");
}

for (const viewport of VIEWPORTS) {
  test(`Round scores stays responsive on ${viewport.name}`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await page.emulateMedia({ reducedMotion: "reduce" });
    await openRoundScores(page);

    const overflow = await page.evaluate(() => ({
      clientWidth: document.documentElement.clientWidth,
      scrollWidth: document.documentElement.scrollWidth,
    }));
    expect(overflow.scrollWidth, "the admin page should not scroll horizontally").toBeLessThanOrEqual(overflow.clientWidth + 1);

    const kpiBoxes = await page.locator(".round-scores-kpis article").evaluateAll((elements) => elements.map((element) => {
      const box = element.getBoundingClientRect();
      return { x: Math.round(box.x), y: Math.round(box.y) };
    }));
    expect(kpiBoxes).toHaveLength(4);
    expect(new Set(kpiBoxes.map((box) => box.x)).size).toBe(viewport.kpiColumns);

    await expect(page.locator(".round-scores-chart canvas")).toBeVisible();
    const chartScroll = page.locator(".round-scores-chart-scroll");
    const chartSizing = await chartScroll.evaluate((element) => ({ clientWidth: element.clientWidth, scrollWidth: element.scrollWidth }));
    if (viewport.width < 600) expect(chartSizing.scrollWidth).toBeGreaterThan(chartSizing.clientWidth);
    await expect(page.getByRole("table", { name: /Round scores for At the market/ })).toBeVisible();
    const incompleteRow = page.getByRole("row").filter({ hasText: "Student 02" });
    await expect(incompleteRow.getByText("Not completed")).toHaveCount(2);
    await expect(incompleteRow.getByText("0%", { exact: true })).toHaveCount(0);

    const statusFilter = page.getByRole("combobox", { name: "Student status" });
    await statusFilter.focus();
    await page.keyboard.press("End");
    await expect(statusFilter).toHaveValue("all");

    const search = page.getByRole("searchbox", { name: "Search students" });
    await search.focus();
    await search.fill("inactive-01");
    await expect(page.getByRole("rowheader", { name: /Inactive Student/ })).toBeVisible();

    const tableScroll = page.locator(".round-scores-table-scroll");
    const tableSizing = await tableScroll.evaluate((element) => ({ clientWidth: element.clientWidth, scrollWidth: element.scrollWidth }));
    if (viewport.width < 600) expect(tableSizing.scrollWidth).toBeGreaterThan(tableSizing.clientWidth);
  });
}
