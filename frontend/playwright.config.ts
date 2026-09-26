import { defineConfig } from "@playwright/test";
import path from "node:path";

const fakeAudio = process.env.E2E_VOICE_AUDIO;

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  fullyParallel: false,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: process.env.E2E_BASE_URL || "http://localhost:5173",
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
    launchOptions: {
      args: [
        "--use-fake-ui-for-media-stream",
        "--use-fake-device-for-media-stream",
        ...(fakeAudio ? [`--use-file-for-fake-audio-capture=${path.resolve(fakeAudio)}`] : []),
      ],
    },
    permissions: ["microphone"],
  },
  projects: [
    { name: "chromium", use: { channel: undefined } },
  ],
});
