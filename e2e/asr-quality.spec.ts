/**
 * ASR quality smoke test — uploads a real recorded WAV file through the
 * VoiceTestPage "Import WAV file" flow and asserts that the backend returns
 * a non-empty transcription + numeric Praat metrics.
 *
 * Does NOT need a microphone: it uploads via the file-input element.
 */

import { test, expect } from "@playwright/test";
import path from "path";
import { fileURLToPath } from "url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const AUDIO_FILE = path.resolve(
  __dirname,
  "../backend/uploads/audio/audio-1781426148542.wav",
);

test.describe("ASR quality — import WAV flow", () => {
  test.setTimeout(120_000);

  test.beforeEach(async ({ page }) => {
    // Seed student session so the voice-test route loads immediately
    await page.addInitScript(() => {
      localStorage.setItem("activeRole", "student");
      localStorage.setItem(
        "studentSession",
        JSON.stringify({ name: "ASR Test Student" }),
      );
    });
    await page.goto("/voice-test");
  });

  test("import WAV → transcription + Praat metrics appear", async ({ page }) => {
    // Upload the WAV file via the hidden input
    const fileInput = page.locator('input[type="file"].voice-file-input');
    await fileInput.setInputFiles(AUDIO_FILE);

    // The page shows "Running Praat and local feedback..." while analyzing
    // Wait up to 60 s for the metrics panel to appear
    await expect(page.locator(".voice-feedback-panel")).toBeVisible({
      timeout: 60_000,
    });

    // --- Transcription ---------------------------------------------------------
    const transcription = await page
      .locator(".voice-feedback-panel")
      .textContent();
    console.log("\n=== FULL FEEDBACK PANEL TEXT ===\n", transcription);

    // --- Score cards -----------------------------------------------------------
    const fluencyText = await page
      .locator(".voice-score-card", { hasText: "Fluency" })
      .textContent();
    const toneText = await page
      .locator(".voice-score-card", { hasText: "Tone accuracy" })
      .textContent();
    const rateText = await page
      .locator(".voice-score-card", { hasText: "Speech rate" })
      .textContent();

    console.log("Fluency  :", fluencyText?.trim());
    console.log("Tone     :", toneText?.trim());
    console.log("Rate     :", rateText?.trim());

    // Extract numeric values and assert they are reasonable
    const fluencyMatch = fluencyText?.match(/(\d+)/);
    const toneMatch = toneText?.match(/(\d+)/);
    const rateMatch = rateText?.match(/([\d.]+)/);

    const fluency = fluencyMatch ? parseInt(fluencyMatch[1]) : null;
    const tone = toneMatch ? parseInt(toneMatch[1]) : null;
    const rate = rateMatch ? parseFloat(rateMatch[1]) : null;

    expect(fluency, "Fluency score should be 0-100").toBeGreaterThanOrEqual(0);
    expect(fluency, "Fluency score should be 0-100").toBeLessThanOrEqual(100);
    expect(tone, "Tone accuracy should be 0-100").toBeGreaterThanOrEqual(0);
    expect(tone, "Tone accuracy should be 0-100").toBeLessThanOrEqual(100);
    expect(rate, "Speech rate should be positive").toBeGreaterThan(0);

    // --- AI feedback (optional — may not be present on every backend) ----------
    const aiPanel = page.locator(".voice-ai-feedback, .story-ai-summary").first();
    if (await aiPanel.isVisible({ timeout: 3_000 }).catch(() => false)) {
      const aiText = await aiPanel.textContent();
      console.log("\n=== AI FEEDBACK ===\n", aiText?.trim());
    } else {
      console.log("\n[AI feedback panel not present — backend may not return it on this route]");
    }

    // --- Word prosody ----------------------------------------------------------
    const wordCards = page.locator(".word-prosody-card, .saved-word-prosody-card");
    const wordCount = await wordCards.count();
    console.log(`\nWord prosody cards: ${wordCount}`);
    if (wordCount > 0) {
      for (let i = 0; i < Math.min(wordCount, 5); i++) {
        const text = await wordCards.nth(i).textContent();
        console.log(`  word[${i}]:`, text?.replace(/\s+/g, " ").trim());
      }
    }
  });

  test("import WAV → transcribed text is non-empty", async ({ page }) => {
    const fileInput = page.locator('input[type="file"].voice-file-input');
    await fileInput.setInputFiles(AUDIO_FILE);

    await expect(page.locator(".voice-feedback-panel")).toBeVisible({
      timeout: 60_000,
    });

    // The transcription text is shown inside ModelExampleCard or a transcription block
    const bodyText = await page.locator(".voice-feedback-panel").textContent();
    // Should contain at least one CJK character (Mandarin transcript)
    const hasCJK = /[一-鿿]/.test(bodyText || "");
    console.log("\nTranscription contains CJK:", hasCJK);
    console.log("Feedback panel text (first 400 chars):", bodyText?.slice(0, 400));
    expect(hasCJK, "Transcription should contain Mandarin characters").toBe(true);
  });
});
