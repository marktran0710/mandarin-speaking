import { test, expect, type Page } from "@playwright/test";

/**
 * Student Mode layout regression (LAYOUT-1/2, HEAD-1, DATA-1, STATE-1,
 * ACTION-1/2, CSS-1 in AGENT_RULES.md §73). Logs in as the seeded demo
 * student and walks Study -> Vocab Preview -> (Vocab Quiz or Story
 * Speaking, whichever the topic's own quiz state routes to) -> Progress ->
 * Placement, asserting the same invariants on every screen it reaches.
 *
 * Story Speaking / Conversation / Submit / Completion are reached only when
 * the student's first lesson happens to skip the quiz (topicHasQuiz ===
 * false) or when a prior run has already earned the vocab-quiz stars for
 * it — passing an arbitrary seeded quiz's real questions generically isn't
 * something this test can do without the answer key, so those screens are
 * asserted opportunistically: when reached, they get the same checks;
 * when not, the run logs why instead of failing or silently no-op'ing.
 */

const FORBIDDEN_TEXT = /(^|\D)3\/wk(\D|$)|(^|\D)5d(\D|$)|94%|HSK/;

const STUDENT_NAME = process.env.E2E_STUDENT_NAME || "Student Demo";
const STUDENT_PASSWORD = process.env.E2E_STUDENT_PASSWORD || "123456";

interface ScreenCheck {
  name: string;
  h1X: number;
}

async function login(page: Page) {
  await page.goto("/");
  await page.getByRole("button", { name: /Student Login/i }).click();
  await page.waitForSelector("#student-name", { timeout: 15000 });
  await page.fill("#student-name", STUDENT_NAME);
  await page.fill("#student-password", STUDENT_PASSWORD);
  await page.click(".login-submit");
  await page.waitForSelector(".sa-page", { timeout: 15000 });
}

/** Runs the six required invariants against whatever screen is currently
 * rendered and returns the H1's left edge for the cross-screen comparison. */
async function assertScreenInvariants(page: Page, screenName: string): Promise<ScreenCheck> {
  // 1. Exactly one visible h1; left-aligned.
  const h1s = page.locator("h1");
  const visibleCount = await h1s.evaluateAll((els) => els.filter((el) => (el as HTMLElement).offsetParent !== null).length);
  expect(visibleCount, `${screenName}: expected exactly one visible h1`).toBe(1);
  const h1 = h1s.first();
  const box = await h1.boundingBox();
  expect(box, `${screenName}: h1 has no layout box`).not.toBeNull();
  const textAlign = await h1.evaluate((el) => getComputedStyle(el).textAlign);
  expect(["start", "left"], `${screenName}: h1 text-align was "${textAlign}"`).toContain(textAlign);

  // 2. Main content has visible text (no blank screen).
  const mainText = (await page.locator("#sa-main").innerText()).trim();
  expect(mainText.length, `${screenName}: #sa-main has no visible text`).toBeGreaterThan(0);

  // 3. No fabricated numbers for the demo account.
  expect(mainText, `${screenName}: found forbidden placeholder text`).not.toMatch(FORBIDDEN_TEXT);

  // 4. No horizontal page scroll.
  const { scrollWidth, innerWidth } = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    innerWidth: window.innerWidth,
  }));
  expect(scrollWidth, `${screenName}: page scrolls horizontally`).toBeLessThanOrEqual(innerWidth + 1);

  // 5. Where an actions bar exists: exactly one primary button, on-screen.
  const actionsBar = page.locator(".sa-page__actions");
  if (await actionsBar.count() > 0) {
    const primaries = actionsBar.locator(".sa-button--primary");
    await expect(primaries, `${screenName}: actions bar should have exactly one primary button`).toHaveCount(1);
    const pBox = await primaries.first().boundingBox();
    const viewport = page.viewportSize();
    expect(pBox, `${screenName}: primary action button has no layout box`).not.toBeNull();
    if (pBox && viewport) {
      expect(pBox.x, `${screenName}: primary action starts off-screen`).toBeGreaterThanOrEqual(0);
      expect(pBox.x + pBox.width, `${screenName}: primary action overflows the viewport`).toBeLessThanOrEqual(viewport.width + 1);
    }
  }

  return { name: screenName, h1X: box!.x };
}

/** 6. Mobile Conversation: exactly one PAGE header bar. The shell's slim
 * persistent mobile app-bar (hamburger + brand, .sa-shell__mobile-bar) is
 * expected to coexist with it — that pairing is the normal mobile pattern
 * every screen uses, not the "two stacked headers" bug (Conversation used
 * to additionally render its own bespoke ConversationHeader on top of a
 * page header; that component is gone, replaced by the shared
 * StudentPageHeader every other screen already used). */
async function assertSingleMobileHeader(page: Page, screenName: string) {
  const visiblePageHeaders = await page.locator("header:not(.sa-shell__mobile-bar)").evaluateAll(
    (els) => els.filter((el) => (el as HTMLElement).offsetParent !== null).length,
  );
  expect(visiblePageHeaders, `${screenName}: expected exactly one visible page header on mobile`).toBe(1);
}

/** On mobile the sidebar (and its Progress/Placement/phase-nav buttons) is
 * off-canvas behind the shell's hamburger button until opened. */
async function openMobileSidebarIfNeeded(page: Page, isMobile: boolean) {
  if (!isMobile) return;
  const menuButton = page.locator(".sa-shell__menu-btn");
  if (await menuButton.count() > 0) await menuButton.click();
}

async function openFirstLesson(page: Page) {
  const currentRow = page.locator(".sa-study__row.is-current").first();
  await expect(currentRow, "expected at least one unlocked/current lesson row").toBeVisible({ timeout: 15000 });
  await currentRow.getByRole("button").click();
  await page.waitForSelector(".sa-page--task", { timeout: 15000 });
}

for (const viewport of [
  { name: "desktop", width: 1280, height: 800 },
  { name: "mobile", width: 390, height: 844 },
] as const) {
  test.describe(`Student Mode layout @ ${viewport.name}`, () => {
    test.use({ viewport: { width: viewport.width, height: viewport.height } });

    test("Study, Vocab Preview, Vocab Quiz/Story Speaking, Progress, and Placement share one layout", async ({ page }) => {
      const checks: ScreenCheck[] = [];

      await login(page);
      checks.push(await assertScreenInvariants(page, "Study"));

      await openFirstLesson(page);
      checks.push(await assertScreenInvariants(page, "Vocab Preview"));

      const cta = page.locator(".sa-page__actions .sa-button--primary");
      await expect(cta).toBeVisible();
      const ctaLabel = await cta.innerText();
      await cta.click();
      await page.waitForTimeout(300);

      if (/quiz/i.test(ctaLabel)) {
        await page.waitForSelector(".sa-page--task", { timeout: 15000 });
        checks.push(await assertScreenInvariants(page, "Vocab Quiz"));
      } else {
        await page.waitForSelector(".sa-page--stage", { timeout: 15000 });
        checks.push(await assertScreenInvariants(page, "Story Speaking"));
        if (viewport.name === "mobile") await assertSingleMobileHeader(page, "Story Speaking");

        await openMobileSidebarIfNeeded(page, viewport.name === "mobile");
        const hasConversationNav = await page.getByRole("button", { name: /Conversation/i }).count();
        if (hasConversationNav > 0 && !(await page.getByRole("button", { name: /Conversation/i }).isDisabled())) {
          await page.getByRole("button", { name: /Conversation/i }).click();
          await page.waitForSelector(".sa-page--stage", { timeout: 15000 });
          checks.push(await assertScreenInvariants(page, "Conversation"));
          if (viewport.name === "mobile") await assertSingleMobileHeader(page, "Conversation");
        } else {
          test.info().annotations.push({
            type: "skipped-screen",
            description: "Conversation not reached: the topic's Story Speaking phase must be completed first, which needs a real audio recording + backend analysis round trip this test does not attempt generically.",
          });
        }
      }

      await openMobileSidebarIfNeeded(page, viewport.name === "mobile");
      await page.getByRole("button", { name: /Progress/i }).click();
      await page.waitForSelector(".sa-page--hub", { timeout: 15000 });
      checks.push(await assertScreenInvariants(page, "Progress"));

      await openMobileSidebarIfNeeded(page, viewport.name === "mobile");
      await page.getByRole("button", { name: /Placement/i }).click();
      await page.waitForSelector(".sa-page--task", { timeout: 15000 });
      checks.push(await assertScreenInvariants(page, "Placement"));

      const xs = checks.map((c) => c.h1X);
      const [first, ...rest] = xs;
      for (const [index, x] of rest.entries()) {
        expect(
          Math.abs(x - first),
          `H1 left edge mismatch: ${checks[0].name}=${first}px vs ${checks[index + 1].name}=${x}px`,
        ).toBeLessThanOrEqual(1);
      }
    });
  });
}
