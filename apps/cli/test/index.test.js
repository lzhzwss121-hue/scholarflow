import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import {
  deriveServiceStatus,
  printStatus,
  probeServiceHealth,
  startServices,
} from "../src/index.js";


test("start repairs missing Web and worker while preserving a running API", async () => {
  const workspace = fs.mkdtempSync(path.join(os.tmpdir(), "scholarflow-cli-"));
  const started = [];
  let writtenState = null;
  const currentState = {
    services: {
      api: {
        pid: 101,
        url: "http://127.0.0.1:8000",
        log: "api.log",
      },
      web: {
        pid: 202,
        url: "http://127.0.0.1:5173",
        log: "web.log",
      },
    },
  };

  const state = await startServices(
    {
      workspace,
      host: "127.0.0.1",
      apiPort: 8000,
      webPort: 5173,
    },
    {
      readStateFn: () => currentState,
      writeStateFn: (_path, value) => {
        writtenState = value;
      },
      isProcessRunningFn: (pid) => pid === 101,
      startServiceFn: (name, command, args, options) => {
        started.push({ name, command, args, options });
        return {
          pid: name === "web" ? 303 : 404,
          command: [command, ...args].join(" "),
          log: `${name}.log`,
          url: options.url,
          startedAt: "2026-07-28T00:00:00.000Z",
        };
      },
    },
  );

  assert.deepEqual(started.map((item) => item.name), ["web", "worker"]);
  assert.equal(state.services.api.pid, currentState.services.api.pid);
  assert.equal(state.services.api.command, currentState.services.api.command);
  assert.equal(writtenState.services.worker.pid, 404);
  assert.ok(
    started
      .find((item) => item.name === "worker")
      .args.includes("scholarflow_api.jobs.worker"),
  );
});


test("status reports PID and health mismatches instead of trusting the PID", async () => {
  assert.equal(deriveServiceStatus(true, false), "unhealthy");
  assert.equal(deriveServiceStatus(false, true), "pid-mismatch");
  assert.equal(deriveServiceStatus(true, true), "running");

  const workerProbe = await probeServiceHealth(
    "worker",
    {
      pid: 22,
      workerId: "expected-worker",
      url: "http://127.0.0.1:8000/health/jobs",
    },
    {
      services: {
        api: { url: "http://127.0.0.1:8000" },
      },
    },
    async () => ({
      ok: true,
      json: async () => ({
        status: "degraded",
        workers: [
          {
            worker_id: "different-worker",
            healthy: true,
          },
        ],
      }),
    }),
  );

  assert.equal(workerProbe.healthy, false);
  assert.match(workerProbe.message, /heartbeat is missing or stale/);
});


test("status command returns unhealthy when PID exists but HTTP health fails", async () => {
  const workspace = fs.mkdtempSync(path.join(os.tmpdir(), "scholarflow-status-"));
  fs.writeFileSync(path.join(workspace, "config.yaml"), "version: 1\n");
  const logs = [];
  const originalLog = console.log;
  console.log = (...values) => logs.push(values.join(" "));
  try {
    const healthy = await printStatus(
      {
        root: workspace,
        config: path.join(workspace, "config.yaml"),
        database: path.join(workspace, "cache", "scholarflow.sqlite3"),
      },
      {
        services: {
          api: {
            pid: 77,
            url: "http://127.0.0.1:8000",
            log: "api.log",
          },
        },
      },
      {
        isProcessRunningFn: () => true,
        fetchFn: async () => {
          throw new Error("connection refused");
        },
      },
    );
    assert.equal(healthy, false);
    assert.ok(logs.some((line) => line.includes("api: unhealthy")));
    assert.ok(logs.some((line) => line.includes("connection refused")));
  } finally {
    console.log = originalLog;
  }
});
