import { existsSync } from "node:fs";
import path from "node:path";

import { defineConfig } from "@playwright/test";

const port = 8766;
const localPython = process.platform === "win32"
  ? path.resolve("../.venv/Scripts/python.exe")
  : path.resolve("../.venv/bin/python");
const python = process.env.VEXPLORER_TEST_PYTHON
  ?? (existsSync(localPython) ? localPython : "python");
const quotedPython = `"${python.replaceAll('"', '\\"')}"`;

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  timeout: 45_000,
  expect: { timeout: 10_000 },
  reporter: process.env.CI
    ? [["line"], ["html", { outputFolder: "playwright-report", open: "never" }]]
    : "line",
  outputDir: "test-results",
  use: {
    baseURL: `http://127.0.0.1:${port}`,
    browserName: "chromium",
    headless: true,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  webServer: {
    command: `${quotedPython} e2e/support/server.py --port ${port}`,
    url: `http://127.0.0.1:${port}/api/v1/health`,
    cwd: ".",
    reuseExistingServer: false,
    timeout: 60_000,
  },
});
