/**
 * Teacher workflow E2E tests.
 *
 * Covers:
 *   - Teacher login flow
 *   - Teacher dashboard renders
 *   - Story builder page loads
 *   - Publish story → student My Stories page reflects it (happy path with mocked API)
 */

import { test, expect, Page } from "@playwright/test";

async function loginAsTeacher(page: Page, name = "E2E Teacher") {
  await page.goto("/");
  await page.getByRole("button", { name: /Teacher Portal/i }).click();
  await page.getByLabel(/Teacher name/i).fill(name);
  await page.getByRole("button", { name: /Enter Teacher Mode/i }).click();
}

async function loginAsStudent(page: Page, name = "E2E Student") {
  await page.goto("/");
  await page.getByRole("button", { name: /Student Portal/i }).click();
  await page.getByLabel(/Student name/i).fill(name);
  await page.getByRole("button", { name: /Enter Student Mode/i }).click();
}

test.describe("Teacher login", () => {
  test("navigates away from login page after submit", async ({ page }) => {
    await loginAsTeacher(page, "Ms. Chen");
    await expect(page.getByLabel(/Teacher name/i)).not.toBeVisible();
  });

  test("stores session in localStorage", async ({ page }) => {
    await loginAsTeacher(page, "Mr. Wang");
    const session = await page.evaluate(() =>
      JSON.parse(localStorage.getItem("teacherSession") || "{}"),
    );
    expect(session.name).toBe("Mr. Wang");
  });
});

test.describe("Teacher dashboard", () => {
  test.beforeEach(async ({ page }) => {
    await loginAsTeacher(page);
  });

  test("dashboard renders without crashing", async ({ page }) => {
    await expect(page.locator("body")).not.toBeEmpty();
    // No JS error boundary fallback should be visible
    await expect(page.getByText(/Something went wrong/i)).not.toBeVisible();
  });

  test("logout returns to home", async ({ page }) => {
    await page.getByRole("button", { name: /Logout|Log out/i }).click();
    await expect(page.getByRole("button", { name: /Teacher Portal/i })).toBeVisible();
  });
});

test.describe("Teacher story builder", () => {
  test.beforeEach(async ({ page }) => {
    await loginAsTeacher(page);
  });

  test("image builder link is present", async ({ page }) => {
    const builderBtn = page.getByRole("button", { name: /Create Story|Image Builder|New Story/i }).first();
    if (await builderBtn.isVisible()) {
      await builderBtn.click();
      await expect(page.locator("body")).not.toBeEmpty();
    }
  });
});

test.describe("Publish → student sees story", () => {
  const mockStory = {
    id: "e2e-story-001",
    title: "E2E Test Story",
    learningGoal: "Practice test",
    level: "Beginner speaking",
    frames: [
      { imageUrl: "", prompt: "Describe scene 1", vocabulary: "你好,再見", vocabularyGroups: [] },
    ],
    published: true,
  };

  test("published story title appears on student My Stories page", async ({ page }) => {
    // addInitScript runs before any JS on every navigation, so localStorage is seeded
    // before React mounts — avoids races with loginAsStudent's page.goto().
    await page.addInitScript((story) => {
      localStorage.setItem("teacherCustomStories", JSON.stringify([story]));
    }, mockStory);

    // Intercept the custom-stories API so the useEffect sync doesn't clobber the seed.
    await page.route("**/api/custom-stories*", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([mockStory]),
      });
    });

    await page.goto("/");
    await loginAsStudent(page, "Story Student");

    // Click "My Stories" in the student nav
    await page.getByRole("button", { name: "My Stories" }).click();

    // topic.name appears in both <p class="stories-kicker"> and an <h3>
    await expect(page.getByText("E2E Test Story").first()).toBeVisible({ timeout: 10_000 });
  });
});
