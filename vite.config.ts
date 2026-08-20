/// <reference types="vitest" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { resolve } from "node:path";

export default defineConfig({
  base: process.env.VITE_BASE_PATH || "/",
  plugins: [react()],
  server: {
    port: 5173,
    open: process.env.VITE_OPEN_BROWSER !== "false",
    // Keep the local development host allowlist explicit instead of disabling
    // Vite's host check globally.
    allowedHosts: [
      "localhost",
      "127.0.0.1",
    ],
    // Proxying /api and /uploads makes the browser see frontend+backend as
    // one origin, so the httpOnly session cookie (backend/auth.py) is sent
    // on every request - a plain cross-port fetch is cross-origin, and
    // Chrome silently refuses to attach the cookie to those (confirmed via
    // manual testing: same-origin fetch worked, cross-port fetch got 401
    // on every identity-gated route even with correct CORS/SameSite=Lax
    // headers). Override the target with BACKEND_PROXY_TARGET for a
    // non-default backend port.
    proxy: {
      "/api": process.env.BACKEND_PROXY_TARGET || "http://127.0.0.1:8000",
      "/uploads": process.env.BACKEND_PROXY_TARGET || "http://127.0.0.1:8000",
    },
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
