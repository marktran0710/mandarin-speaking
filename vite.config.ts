/// <reference types="vitest" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { resolve } from "node:path";

export default defineConfig({
  base: process.env.VITE_BASE_PATH || "/",
  plugins: [react()],
  server: {
    port: 5173,
    open: true,
    // The student app is opened through the machine's Tailscale hostname
    // during remote QA. Keep the allowlist explicit instead of disabling
    // Vite's host check globally.
    allowedHosts: ["desktop-9417om5.tail7fe66e.ts.net"],
  },
  build: {
    rollupOptions: {
      // Two entry points so `npm run build` emits both dist/index.html
      // (student app) and dist/teacher.html (teacher app) from one Vite project.
      input: {
        main: resolve(__dirname, "index.html"),
        teacher: resolve(__dirname, "teacher.html"),
        admin: resolve(__dirname, "admin.html"),
        demo: resolve(__dirname, "instructor-demo.html"),
      },
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: "./src/test/setup.ts",
    globals: true,
  },
});
