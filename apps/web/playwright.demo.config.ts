import { defineConfig, devices } from "@playwright/test";

/**
 * Records the demo video and the README screenshots (`make demo`), against the stack of
 * compose.e2e.yaml + compose.demo.yaml (real bge-m3 search, fake answers). Not part of CI.
 */
export default defineConfig({
  testDir: "./tests/demo",
  testMatch: "**/*.spec.ts",
  globalSetup: "./tests/e2e/global-setup.ts",
  outputDir: "./demo-output",
  fullyParallel: false,
  retries: 0,
  timeout: 10 * 60_000,
  expect: { timeout: 60_000 },
  reporter: "list",
  use: {
    ...devices["Desktop Chrome"],
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3100",
    viewport: { width: 1280, height: 800 },
    deviceScaleFactor: 1,
    video: { mode: "on", size: { width: 1280, height: 800 } },
  },
});
