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
    // Dev server is reached through whatever tunnel is active at the time
    // (Tailscale Funnel, VS Code port forwarding, ...), each with its own
    // generated hostname - keeping an explicit allowlist meant updating this
    // file (or VITE_ALLOWED_HOSTS) every time the tunnel changed, and a
    // forgotten update surfaces as a confusing "could not load data" error
    // in the app rather than an obvious host-blocked message. This setting
    // is dev-server only (`vite dev`/`preview`); it has no effect on the
    // production build, which Vite never serves.
    allowedHosts: true,
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
      // Keep the legacy student/teacher/admin entries available while the
      // Next.js route shell is being migrated and verified.
      input: {
        main: resolve(import.meta.dirname, "index.html"),
        teacher: resolve(import.meta.dirname, "teacher.html"),
        admin: resolve(import.meta.dirname, "admin.html"),
      },
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: "./src/test/setup.ts",
    globals: true,
  },
});
