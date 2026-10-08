/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  base: "./", // future GitHub Pages readiness; local preview unaffected
  plugins: [react()],
  server: {
    // leanatlas serve in dev: same-origin /api without CORS (spec §2)
    proxy: { "/api": "http://127.0.0.1:8000" },
  },
  test: {
    environment: "node",
    include: ["src/**/*.test.ts"],
  },
});
