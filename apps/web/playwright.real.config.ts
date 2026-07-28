import { defineConfig, devices } from "@playwright/test";

const acceptanceRoot =
  process.env.SCHOLARFLOW_ACCEPTANCE_ROOT ??
  "/private/tmp/scholarflow-real-backend-e2e";
const databasePath =
  process.env.SCHOLARFLOW_DB_PATH ??
  `${acceptanceRoot}/scholarflow.sqlite3`;

const sharedEnv = {
  ...process.env,
  PYTHONPATH: "../../services/api/src",
  SCHOLARFLOW_ACCEPTANCE_ROOT: acceptanceRoot,
  SCHOLARFLOW_AUTO_FETCH_PDF: "0",
  SCHOLARFLOW_DB_PATH: databasePath,
  SCHOLARFLOW_FIXTURE_PORT: "18765",
  SCHOLARFLOW_MODEL_PROVIDER: "local",
};

export default defineConfig({
  testDir: "./e2e",
  testMatch: /real-backend\.spec\.ts/,
  outputDir: `${acceptanceRoot}/test-results`,
  timeout: 120_000,
  expect: {
    timeout: 20_000,
  },
  use: {
    baseURL: "http://127.0.0.1:15174",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "chromium-real-backend",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: [
    {
      name: "fixture-api",
      command:
        "../../.venv/bin/python e2e/real_backend_harness.py api",
      env: sharedEnv,
      gracefulShutdown: { signal: "SIGTERM", timeout: 2_000 },
      reuseExistingServer: false,
      stderr: "ignore",
      stdout: "ignore",
      timeout: 60_000,
      url: "http://127.0.0.1:18010/health",
    },
    {
      name: "durable-worker",
      command:
        "../../.venv/bin/python e2e/real_backend_harness.py worker",
      env: {
        ...sharedEnv,
        SCHOLARFLOW_WORKER_ID: "playwright-real-worker",
      },
      gracefulShutdown: { signal: "SIGTERM", timeout: 2_000 },
      reuseExistingServer: false,
      stderr: "ignore",
      stdout: "ignore",
      timeout: 60_000,
      url: "http://127.0.0.1:18011/health",
    },
    {
      name: "vite-real",
      command:
        "npm run dev -- --host 127.0.0.1 --port 15174",
      env: {
        ...sharedEnv,
        VITE_SCHOLARFLOW_API_BASE_URL: "http://127.0.0.1:18010",
      },
      gracefulShutdown: { signal: "SIGTERM", timeout: 2_000 },
      reuseExistingServer: false,
      stderr: "ignore",
      stdout: "ignore",
      timeout: 60_000,
      url: "http://127.0.0.1:15174",
    },
  ],
});
