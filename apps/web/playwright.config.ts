import { defineConfig, devices } from "@playwright/test";

const e2eDbPath = process.env.SCHOLARFLOW_DB_PATH ?? "/private/tmp/scholarflow-e2e.sqlite3";
const e2eOutputDir = process.env.PLAYWRIGHT_OUTPUT_DIR ?? "test-results";

export default defineConfig({
  testDir: "./e2e",
  testIgnore: /real-backend\.spec\.ts/,
  outputDir: e2eOutputDir,
  timeout: 60_000,
  expect: {
    timeout: 10_000,
  },
  use: {
    baseURL: "http://127.0.0.1:5173",
    trace: "retain-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: {
    command: "npm run dev -- --host 127.0.0.1",
    env: {
      ...process.env,
      SCHOLARFLOW_DB_PATH: e2eDbPath,
    },
    reuseExistingServer: true,
    timeout: 60_000,
    url: "http://127.0.0.1:5173",
  },
});
