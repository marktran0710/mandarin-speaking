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
  },
  build: {
    rollupOptions: {
      // Two entry points so `npm run build` emits both dist/index.html
      // (student app) and dist/teacher.html (teacher app) from one Vite project.
      input: {
        main: resolve(__dirname, "index.html"),
        teacher: resolve(__dirname, "teacher.html"),
      },
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: "./src/test/setup.ts",
    globals: true,
  },
});
