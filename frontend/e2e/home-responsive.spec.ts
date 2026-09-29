import { expect, test, type Locator, type Page } from "@playwright/test";

const VIEWPORTS = [
  { name: "wide desktop", width: 1440, height: 900 },
  { name: "laptop", width: 1280, height: 800 },
  { name: "small desktop", width: 1024, height: 768 },
  { name: "breakpoint plus", width: 901, height: 800 },
  { name: "breakpoint", width: 900, height: 800 },
  { name: "tablet", width: 768, height: 1024 },
  { name: "large mobile", width: 430, height: 932 },
  { name: "mobile", width: 390, height: 844 },
  { name: "small mobile", width: 320, height: 568 },
] as const;

interface Rect {
  x: number;
  y: number;
  width: number;
  height: number;
}

async function rect(locator: Locator, label: string): Promise<Rect> {
  const box = await locator.boundingBox();
  expect(box, `${label} should have a layout box`).not.toBeNull();
  return box!;
}

function right(box: Rect) {
  return box.x + box.width;
}

function bottom(box: Rect) {
  return box.y + box.height;
}

async function openHome(page: Page) {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/");
  await page.locator(".home-page").waitFor();
  await page.evaluate(() => document.fonts.ready);
}

for (const viewport of VIEWPORTS) {
  test(`Home layout stays readable at ${viewport.name} (${viewport.width}x${viewport.height})`, async ({ page }) => {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await openHome(page);

    const overflow = await page.evaluate(() => ({
      clientWidth: document.documentElement.clientWidth,
      scrollWidth: document.documentElement.scrollWidth,
    }));
    expect(overflow.scrollWidth, "page should not scroll horizontally").toBeLessThanOrEqual(overflow.clientWidth + 1);

    const hero = await rect(page.locator(".home-hero"), "hero");
    const copy = await rect(page.locator(".home-hero-copy"), "hero copy");
    const stage = await rect(page.locator(".story-preview-stage"), "story preview");
    const focus = await rect(page.locator(".practice-focus"), "learning focus");
    const focusHeading = await rect(page.locator(".practice-focus-heading"), "learning focus heading");
    const focusGrid = await rect(page.locator(".practice-focus-grid"), "learning focus cards");
    const footer = await rect(page.locator(".source-attribution"), "source attribution");

    expect(bottom(hero), "hero must contain both columns").toBeGreaterThanOrEqual(Math.max(bottom(copy), bottom(stage)) - 1);
    expect(focus.y, "learning focus must start after hero content").toBeGreaterThanOrEqual(Math.max(bottom(copy), bottom(stage)) - 1);
    expect(bottom(focus), "learning focus must contain its heading and cards").toBeGreaterThanOrEqual(
      Math.max(bottom(focusHeading), bottom(focusGrid)) - 1,
    );
    expect(footer.y, "footer must start after learning focus").toBeGreaterThanOrEqual(bottom(focus) - 1);

    if (viewport.width >= 961) {
      expect(stage.x, "desktop preview should sit beside the hero copy").toBeGreaterThanOrEqual(right(copy) + 16);
    } else {
      expect(stage.y, "tablet preview should stack below the hero copy").toBeGreaterThanOrEqual(bottom(copy) + 16);
    }

    if (viewport.width >= 1180) {
      expect(focusGrid.x, "wide desktop cards should sit beside the heading").toBeGreaterThanOrEqual(right(focusHeading) + 16);
    } else {
      expect(focusGrid.y, "compact layouts should place cards below the heading").toBeGreaterThanOrEqual(bottom(focusHeading) + 16);
    }

    const cards = await page.locator(".practice-focus-card").evaluateAll((elements) => elements.map((element) => {
      const box = element.getBoundingClientRect();
      return { x: box.x, y: box.y, width: box.width, height: box.height };
    }));
    expect(cards).toHaveLength(3);
    if (viewport.width >= 721) {
      expect(Math.max(...cards.map((card) => card.y)) - Math.min(...cards.map((card) => card.y))).toBeLessThanOrEqual(1);
      expect(cards[1].x).toBeGreaterThan(right(cards[0]) - 1);
      expect(cards[2].x).toBeGreaterThan(right(cards[1]) - 1);
    } else {
      expect(Math.max(...cards.map((card) => card.x)) - Math.min(...cards.map((card) => card.x))).toBeLessThanOrEqual(1);
      expect(cards[1].y).toBeGreaterThanOrEqual(bottom(cards[0]) + 8);
      expect(cards[2].y).toBeGreaterThanOrEqual(bottom(cards[1]) + 8);
    }

    const navButtons = page.locator(".navbar-menu-student .nav-link");
    await expect(navButtons).toHaveCount(3);
    for (let index = 0; index < 3; index += 1) {
      const button = await rect(navButtons.nth(index), `navbar button ${index + 1}`);
      expect(button.x).toBeGreaterThanOrEqual(0);
      expect(right(button)).toBeLessThanOrEqual(viewport.width + 1);
      expect(button.height).toBeGreaterThanOrEqual(44);
    }

    const cta = page.getByRole("button", { name: "開始學習" });
    await expect(cta).toBeVisible();
    const ctaBox = await rect(cta, "start learning action");
    expect(ctaBox.x).toBeGreaterThanOrEqual(0);
    expect(right(ctaBox)).toBeLessThanOrEqual(viewport.width + 1);

    if (viewport.width <= 360) {
      const iconDisplay = await page.locator(".navbar-menu-student .nav-link-icon").first().evaluate(
        (element) => getComputedStyle(element).display,
      );
      expect(iconDisplay).toBe("none");
    }
  });
}

test("Home navigation, CTA, and theme controls keep their behavior", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await openHome(page);

  const homeNav = page.getByRole("button", { name: "首頁" });
  await expect(homeNav).toHaveAttribute("aria-current", "page");

  const lightCanvas = await page.locator(".app-container").evaluate((element) => getComputedStyle(element).backgroundColor);
  await page.getByRole("button", { name: "深色" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await expect(page.getByRole("button", { name: "亮色" })).toBeVisible();
  await expect.poll(
    () => page.locator(".app-container").evaluate((element) => getComputedStyle(element).backgroundColor),
  ).toBe("rgb(27, 23, 18)");
  expect(lightCanvas).not.toBe("rgb(27, 23, 18)");
  await expect.poll(
    () => page.locator(".hero-title").evaluate((element) => getComputedStyle(element).color),
  ).toBe("rgb(244, 239, 226)");

  await page.getByRole("button", { name: "學生登入" }).click();
  await expect(page.getByRole("heading", { name: "學生登入" })).toBeVisible();
  await expect(page.getByRole("button", { name: "學生登入" })).toHaveAttribute("aria-current", "page");

  await page.getByRole("button", { name: /慢慢中文 logo/ }).click();
  await expect(page.getByRole("heading", { name: /慢慢中文/ })).toBeVisible();

  await page.getByRole("button", { name: "開始學習" }).click();
  await expect(page.getByRole("heading", { name: "學生登入" })).toBeVisible();
});
