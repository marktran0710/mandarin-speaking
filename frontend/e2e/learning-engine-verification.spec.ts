import { test, expect, type Page } from "@playwright/test";

const enabled = process.env.E2E_VERIFY_LEARNING_ENGINE === "1";
const studentName = process.env.E2E_STUDENT_NAME || "Student Demo";
const studentPassword = process.env.E2E_STUDENT_PASSWORD || "123456";
const storyName = process.env.E2E_STORY_NAME;
const expectedWeakWord = process.env.E2E_EXPECTED_WEAK_WORD;
const expectedDueWord = process.env.E2E_EXPECTED_DUE_WORD;
const voiceAudio = process.env.E2E_VOICE_AUDIO;

test.describe("learning engine live verification", () => {
  test.skip(!enabled, "Set E2E_VERIFY_LEARNING_ENGINE=1 to run against seeded published data.");

  async function login(page: Page) {
    await page.goto("/");
    await page.getByRole("button", { name: /Student Login/i }).click();
    await page.waitForSelector("#student-name");
    await page.fill("#student-name", studentName);
    await page.fill("#student-password", studentPassword);
    await page.click(".login-submit");
    await page.waitForSelector(".sa-page", { timeout: 20_000 });
  }

  async function openLesson(page: Page) {
    test.skip(!storyName, "Set E2E_STORY_NAME to a published lesson.");
    const row = page.locator(".study-row").filter({ hasText: storyName! }).first();
    await expect(row).toBeVisible({ timeout: 20_000 });
    await row.getByRole("button").click();
    await page.waitForSelector(".sa-page--task", { timeout: 20_000 });
  }

  async function openQuizModes(page: Page) {
    const start = page.locator(".sa-page__actions .sa-button--primary");
    await expect(start).toBeVisible();
    await start.click();
    await page.waitForSelector(".sa-quiz__mode-layout, .sa-quiz__question-column", { timeout: 20_000 });
    if (await page.locator(".sa-quiz__mode-layout").count() === 0) {
      throw new Error("Lesson did not reach the quiz mode picker; complete/persist its diagnostic rounds first.");
    }
  }

  test("BKT-ranked weak word is visible in personalized practice", async ({ page }) => {
    await login(page);
    await openLesson(page);
    const weakResponse = page.waitForResponse((response) => response.url().includes("/weak-words"));
    await openQuizModes(page);
    const payload = await (await weakResponse).json();
    const ranked = payload.words?.[0]?.word;
    expect(ranked, "weak-word API returned no ranked word").toBeTruthy();
    if (expectedWeakWord) expect(ranked).toBe(expectedWeakWord);

    const practice = page.getByRole("button", { name: /Practice weak words/i });
    await expect(practice).toBeEnabled();
    await practice.click();
    await expect(page.locator(".sa-quiz__question-column")).toHaveAttribute("data-verification-word", ranked);
  });

  test("SM-2 due word is visible in maintenance review", async ({ page }) => {
    await login(page);
    await openLesson(page);
    const queueResponse = page.waitForResponse((response) => response.url().includes("/review-queue"));
    await openQuizModes(page);
    const payload = await (await queueResponse).json();
    const due = payload.queue?.find((entry: { reviewReason?: string }) => entry.reviewReason === "due");
    expect(due?.word, "review queue returned no due word").toBeTruthy();
    if (expectedDueWord) expect(due.word).toBe(expectedDueWord);

    const review = page.getByRole("button", { name: /Review due words/i });
    await expect(review).toBeEnabled();
    await review.click();
    await expect(page.locator(".sa-quiz__question-column")).toHaveAttribute("data-verification-word", due.word);
  });

  test("voice feedback exposes real provider and Praat provenance", async ({ page }) => {
    test.skip(!voiceAudio, "Set E2E_VOICE_AUDIO to a real human WAV recording.");
    await login(page);
    await openLesson(page);

    const speaking = page.getByRole("button", { name: /Story Speaking/i }).first();
    await expect(speaking).toBeEnabled({ timeout: 20_000 });
    await speaking.click();
    await page.waitForSelector(".sa-speaking__action", { timeout: 20_000 });

    const analysisResponse = page.waitForResponse((response) => response.url().includes("/api/analyze"), { timeout: 40_000 });
    await page.getByRole("button", { name: /^Record$/i }).click();
    await page.waitForTimeout(1_500);
    await page.getByRole("button", { name: /Stop/i }).click();
    const response = await analysisResponse;
    expect(response.ok()).toBeTruthy();
    const analysis = await response.json();
    expect(analysis.feedback_provenance?.executed_provider).toBeTruthy();
    expect(analysis.feedback_provenance?.pronunciation_source).toBe("praat_acoustic_measurements");
    await expect(page.getByRole("status").filter({ hasText: /Coach:/i })).toBeVisible({ timeout: 20_000 });
  });
});
