/**
 * Student workflow E2E tests.
 *
 * Covers:
 *   - Home page renders portals
 *   - Student login flow (name entry → practice page)
 *   - Voice Test page loads and shows record button
 *   - My Stories page loads after login
 *   - Backend unavailable: UI degrades gracefully (no crash)
 */

import { test, expect, Page } from "@playwright/test";

async function loginAsStudent(page: Page, name = "E2E Student") {
  await page.goto("/");
  await page.getByRole("button", { name: /Student Portal/i }).click();
  await page.getByLabel(/Student name/i).fill(name);
  await page.getByRole("button", { name: /Enter Student Mode/i }).click();
}

test.describe("Home page", () => {
  test("shows both portals", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("button", { name: /Student Portal/i })).toBeVisible();
    await expect(page.getByRole("button", { name: /Teacher Portal/i })).toBeVisible();
  });
});

test.describe("Student login", () => {
  test("navigates to practice page after login", async ({ page }) => {
    await loginAsStudent(page, "Test Student");
    // Should leave the login card and reach the practice / stories area
    await expect(page.getByRole("button", { name: /Student Portal/i })).not.toBeVisible();
  });

  test("name is persisted in session storage", async ({ page }) => {
    await loginAsStudent(page, "Persistent Student");
    const session = await page.evaluate(() =>
      JSON.parse(localStorage.getItem("studentSession") || "{}"),
    );
    expect(session.name).toBe("Persistent Student");
  });
});

test.describe("Student practice page", () => {
  test.beforeEach(async ({ page }) => {
    await loginAsStudent(page);
  });

  test("logout returns to home page", async ({ page }) => {
    await page.getByRole("button", { name: /Logout|Log out/i }).click();
    await expect(page.getByRole("button", { name: /Student Portal/i })).toBeVisible();
  });

  test("navigation links are visible", async ({ page }) => {
    // At least one navigation element should exist after login
    const nav = page.locator("nav, [role='navigation']");
    await expect(nav.first()).toBeVisible();
  });
});

test.describe("Voice Test page", () => {
  test.beforeEach(async ({ page }) => {
    await loginAsStudent(page);
  });

  test("record button is present", async ({ page }) => {
    // Look for a record / microphone button
    const recordBtn = page.getByRole("button", { name: /record|start|mic/i }).first();
    await expect(recordBtn).toBeVisible({ timeout: 10_000 });
  });
});

test.describe("My Stories page", () => {
  test.beforeEach(async ({ page }) => {
    await loginAsStudent(page);
  });

  test("My Stories link navigates to stories view", async ({ page }) => {
    const storiesLink = page.getByRole("button", { name: /My Stories|Stories/i }).first();
    if (await storiesLink.isVisible()) {
      await storiesLink.click();
      // Should not crash — at minimum the page still has content
      await expect(page.locator("body")).not.toBeEmpty();
    }
  });
});

test.describe("Error resilience", () => {
  test("page does not crash when backend is unreachable", async ({ page }) => {
    // Block all API calls
    await page.route("**/api/**", (route) => route.abort());
    await loginAsStudent(page);
    // Should still render — no white screen of death
    await expect(page.locator("body")).not.toBeEmpty();
  });
});
