#!/usr/bin/env node

import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import process from "node:process";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";

const VERSION = "0.1.0";
const DEFAULT_API_PORT = 8000;
const DEFAULT_WEB_PORT = 5173;
const DEFAULT_HOST = "127.0.0.1";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const REPO_ROOT = path.resolve(__dirname, "../../..");
const WORKSPACE_DIRS = ["projects", "artifacts", "logs", "cache"];
const STATE_FILE_NAME = "services.json";

function printHelp() {
  console.log(`ScholarFlow CLI ${VERSION}

Usage:
  scholarflow init [--workspace <path>] [--force]
  scholarflow start [--workspace <path>] [--host <host>] [--api-port <port>] [--web-port <port>]
  scholarflow stop [--workspace <path>]
  scholarflow status [--workspace <path>]
  scholarflow --version

Workspace resolution:
  1. --workspace <path>
  2. SCHOLARFLOW_WORKSPACE
  3. ~/.scholarflow

Local durable services:
  start 会分别检查并启动 API、Web 与 SQLite worker。
  status 同时核对 PID、HTTP 健康与 worker heartbeat。

Bounded Research Agent:
  支持有预算的 Observe → Reason → Act；local provider 回退确定性工具图，不是无限自治 Agent。
  模型 provider 只从 API 进程环境变量读取；缺少 key 时明确使用 local fallback。`);
}

function parseArgs(argv) {
  const args = {
    command: undefined,
    workspace: undefined,
    host: DEFAULT_HOST,
    apiPort: DEFAULT_API_PORT,
    webPort: DEFAULT_WEB_PORT,
    force: false,
  };

  for (let index = 0; index < argv.length; index += 1) {
    const token = argv[index];
    if (token === "--workspace") {
      args.workspace = readOptionValue(argv, index, token);
      index += 1;
    } else if (token === "--host") {
      args.host = readOptionValue(argv, index, token);
      index += 1;
    } else if (token === "--api-port") {
      args.apiPort = parsePort(readOptionValue(argv, index, token), token);
      index += 1;
    } else if (token === "--web-port") {
      args.webPort = parsePort(readOptionValue(argv, index, token), token);
      index += 1;
    } else if (token === "--force") {
      args.force = true;
    } else if (token === "--version" || token === "-v") {
      args.command = "--version";
    } else if (token === "--help" || token === "-h") {
      args.command = "--help";
    } else if (!args.command) {
      args.command = token;
    } else {
      throw new Error(`Unknown argument: ${token}`);
    }
  }

  return args;
}

function readOptionValue(argv, index, optionName) {
  const value = argv[index + 1];
  if (!value || value.startsWith("--")) {
    throw new Error(`Missing value for ${optionName}`);
  }
  return value;
}

function parsePort(value, optionName) {
  const port = Number(value);
  if (!Number.isInteger(port) || port < 1 || port > 65535) {
    throw new Error(`Invalid port for ${optionName}: ${value}`);
  }
  return port;
}

function expandHome(inputPath) {
  if (inputPath === "~") {
    return os.homedir();
  }
  if (inputPath.startsWith("~/")) {
    return path.join(os.homedir(), inputPath.slice(2));
  }
  return inputPath;
}

function resolveWorkspace(inputWorkspace) {
  const configured = inputWorkspace || process.env.SCHOLARFLOW_WORKSPACE || "~/.scholarflow";
  return path.resolve(expandHome(configured));
}

function getWorkspacePaths(workspacePath) {
  return {
    root: workspacePath,
    config: path.join(workspacePath, "config.yaml"),
    projects: path.join(workspacePath, "projects"),
    artifacts: path.join(workspacePath, "artifacts"),
    logs: path.join(workspacePath, "logs"),
    cache: path.join(workspacePath, "cache"),
    database: path.join(workspacePath, "cache", "scholarflow.sqlite3"),
    state: path.join(workspacePath, "cache", STATE_FILE_NAME),
  };
}

function ensureWorkspace(workspacePath, options = {}) {
  const workspace = getWorkspacePaths(workspacePath);
  fs.mkdirSync(workspace.root, { recursive: true });
  for (const dirName of WORKSPACE_DIRS) {
    fs.mkdirSync(path.join(workspace.root, dirName), { recursive: true });
  }

  if (options.force || !fs.existsSync(workspace.config)) {
    fs.writeFileSync(workspace.config, createDefaultConfig(workspace), "utf8");
  }

  return workspace;
}

function createDefaultConfig(workspace) {
  const relativeDbPath = path.relative(workspace.root, workspace.database);
  return `# ScholarFlow local workspace configuration
version: 1
language: zh-CN

api:
  host: ${DEFAULT_HOST}
  port: ${DEFAULT_API_PORT}

web:
  host: ${DEFAULT_HOST}
  port: ${DEFAULT_WEB_PORT}

database:
  path: ${relativeDbPath}

privacy:
  local_first: true
  commit_workspace_to_git: false
`;
}

function readState(statePath) {
  if (!fs.existsSync(statePath)) {
    return null;
  }

  try {
    return JSON.parse(fs.readFileSync(statePath, "utf8"));
  } catch (error) {
    throw new Error(`Failed to read service state: ${error.message}`);
  }
}

function writeState(statePath, state) {
  fs.writeFileSync(statePath, `${JSON.stringify(state, null, 2)}\n`, "utf8");
}

function clearState(statePath) {
  if (fs.existsSync(statePath)) {
    fs.unlinkSync(statePath);
  }
}

function isProcessRunning(pid) {
  if (!Number.isInteger(pid) || pid <= 0) {
    return false;
  }

  try {
    process.kill(pid, 0);
    return true;
  } catch (error) {
    return error.code === "EPERM";
  }
}

function getServiceStatus(service) {
  if (!service) {
    return "not-started";
  }
  return isProcessRunning(service.pid) ? "running" : "stale";
}

function getPythonCommand() {
  const virtualenvPython = path.join(REPO_ROOT, ".venv", "bin", "python");
  return fs.existsSync(virtualenvPython) ? virtualenvPython : "python3";
}

function getNpmCommand() {
  return process.platform === "win32" ? "npm.cmd" : "npm";
}

function appendEnvPath(existingValue, extraPath) {
  return existingValue ? `${extraPath}${path.delimiter}${existingValue}` : extraPath;
}

function startService(serviceName, command, args, options) {
  const logPath = path.join(options.workspace.logs, `${serviceName}.log`);
  const logFd = fs.openSync(logPath, "a");
  const child = spawn(command, args, {
    cwd: REPO_ROOT,
    env: options.env,
    detached: true,
    stdio: ["ignore", logFd, logFd],
  });
  child.unref();
  fs.closeSync(logFd);

  return {
    pid: child.pid,
    command: [command, ...args].join(" "),
    cwd: REPO_ROOT,
    log: logPath,
    url: options.url,
    startedAt: new Date().toISOString(),
  };
}

async function startServices(args, runtime = {}) {
  const readStateFn = runtime.readStateFn ?? readState;
  const writeStateFn = runtime.writeStateFn ?? writeState;
  const startServiceFn = runtime.startServiceFn ?? startService;
  const isProcessRunningFn = runtime.isProcessRunningFn ?? isProcessRunning;
  const workspacePath = resolveWorkspace(args.workspace);
  const workspace = ensureWorkspace(workspacePath);
  const currentState = readStateFn(workspace.state);

  const apiUrl = `http://${args.host}:${args.apiPort}`;
  const webUrl = `http://${args.host}:${args.webPort}`;
  const pythonPath = path.resolve(REPO_ROOT, "services/api/src");
  const baseEnv = {
    ...process.env,
    SCHOLARFLOW_WORKSPACE: workspace.root,
    SCHOLARFLOW_DB_PATH: workspace.database,
    PYTHONPATH: appendEnvPath(process.env.PYTHONPATH, pythonPath),
  };
  const existingServices = currentState?.services ?? {};
  const startedNames = [];
  const api =
    getServiceStatusWith(existingServices.api, isProcessRunningFn) === "running"
      ? existingServices.api
      : startServiceFn(
          "api",
          getPythonCommand(),
          [
            "-m",
            "uvicorn",
            "scholarflow_api.main:app",
            "--app-dir",
            "services/api/src",
            "--host",
            args.host,
            "--port",
            String(args.apiPort),
          ],
          {
            workspace,
            env: baseEnv,
            url: apiUrl,
          },
        );
  if (api !== existingServices.api) {
    startedNames.push("api");
  }

  const web =
    getServiceStatusWith(existingServices.web, isProcessRunningFn) === "running"
      ? existingServices.web
      : startServiceFn(
          "web",
          getNpmCommand(),
          [
            "--workspace",
            "@scholarflow/web",
            "run",
            "dev",
            "--",
            "--host",
            args.host,
            "--port",
            String(args.webPort),
            "--strictPort",
          ],
          {
            workspace,
            env: {
              ...baseEnv,
              VITE_SCHOLARFLOW_API_BASE_URL: apiUrl,
            },
            url: webUrl,
          },
        );
  if (web !== existingServices.web) {
    startedNames.push("web");
  }

  const workerId =
    existingServices.worker?.workerId ??
    `cli-worker-${Date.now()}-${process.pid}`;
  const worker =
    getServiceStatusWith(existingServices.worker, isProcessRunningFn) === "running"
      ? existingServices.worker
      : {
          ...startServiceFn(
            "worker",
            getPythonCommand(),
            ["-m", "scholarflow_api.jobs.worker"],
            {
              workspace,
              env: {
                ...baseEnv,
                SCHOLARFLOW_WORKER_ID: workerId,
              },
              url: `${apiUrl}/health/jobs?worker_id=${encodeURIComponent(workerId)}`,
            },
          ),
          workerId,
        };
  if (worker !== existingServices.worker) {
    startedNames.push("worker");
  }

  const state = {
    version: VERSION,
    workspace: workspace.root,
    startedAt: new Date().toISOString(),
    services: {
      api: {
        ...api,
        port: args.apiPort,
      },
      web: {
        ...web,
        port: args.webPort,
      },
      worker,
    },
  };
  writeStateFn(workspace.state, state);

  console.log(
    startedNames.length
      ? `ScholarFlow repaired/started: ${startedNames.join(", ")}.`
      : "ScholarFlow API, Web and worker are already running.",
  );
  console.log(`Workspace: ${workspace.root}`);
  console.log(`API: ${apiUrl}`);
  console.log(`Web: ${webUrl}`);
  console.log(`Worker: ${worker.workerId}`);
  console.log(`Logs: ${workspace.logs}`);
  return state;
}

async function stopServices(args) {
  const workspacePath = resolveWorkspace(args.workspace);
  const workspace = getWorkspacePaths(workspacePath);
  const state = readState(workspace.state);

  if (!state?.services) {
    console.log("No ScholarFlow services are recorded for this workspace.");
    console.log(`Workspace: ${workspace.root}`);
    return;
  }

  const services = Object.entries(state.services);
  for (const [name, service] of services) {
    if (!isProcessRunning(service.pid)) {
      console.log(`${name}: already stopped or stale (pid ${service.pid})`);
      continue;
    }

    terminateProcessGroup(service.pid, "SIGTERM");
    console.log(`${name}: stopping pid ${service.pid}`);
  }

  await waitForServicesToStop(services);

  for (const [name, service] of services) {
    if (isProcessRunning(service.pid)) {
      terminateProcessGroup(service.pid, "SIGKILL");
      console.log(`${name}: forced stop pid ${service.pid}`);
    }
  }

  clearState(workspace.state);
  console.log("ScholarFlow services stopped.");
}

function terminateProcessGroup(pid, signal) {
  try {
    if (process.platform === "win32") {
      process.kill(pid, signal);
    } else {
      process.kill(-pid, signal);
    }
  } catch (error) {
    if (error.code !== "ESRCH") {
      throw error;
    }
  }
}

async function waitForServicesToStop(services) {
  const deadline = Date.now() + 5000;
  while (Date.now() < deadline) {
    const stillRunning = services.some(([, service]) => isProcessRunning(service.pid));
    if (!stillRunning) {
      return;
    }
    await new Promise((resolve) => {
      setTimeout(resolve, 250);
    });
  }
}

async function printStatus(workspace, state, runtime = {}) {
  const isProcessRunningFn = runtime.isProcessRunningFn ?? isProcessRunning;
  const fetchFn = runtime.fetchFn ?? globalThis.fetch;
  const initialized = fs.existsSync(workspace.config);
  console.log(`Workspace: ${workspace.root}`);
  console.log(`Initialized: ${initialized ? "yes" : "no"}`);
  console.log(`Config: ${workspace.config}`);
  console.log(`Database: ${workspace.database}`);

  if (!state?.services) {
    console.log("Services: not started");
    return false;
  }

  let healthy = true;
  for (const name of ["api", "web", "worker"]) {
    const service = state.services[name];
    if (!service) {
      healthy = false;
      console.log(`${name}: not-started`);
      console.log("  warning: service is missing from local service state");
      continue;
    }
    const pidRunning = isProcessRunningFn(service.pid);
    const healthResult = await probeServiceHealth(name, service, state, fetchFn);
    const status = deriveServiceStatus(pidRunning, healthResult.healthy);
    const url = service.url ? ` ${service.url}` : "";
    console.log(`${name}: ${status} pid=${service.pid}${url}`);
    console.log(`  log: ${service.log}`);
    if (status !== "running") {
      healthy = false;
      console.log(`  warning: ${healthResult.message}`);
    }
  }
  return healthy;
}

function getServiceStatusWith(service, isProcessRunningFn) {
  if (!service) {
    return "not-started";
  }
  return isProcessRunningFn(service.pid) ? "running" : "stale";
}

function deriveServiceStatus(pidRunning, healthHealthy) {
  if (pidRunning && healthHealthy) {
    return "running";
  }
  if (pidRunning && !healthHealthy) {
    return "unhealthy";
  }
  if (!pidRunning && healthHealthy) {
    return "pid-mismatch";
  }
  return "stale";
}

async function probeServiceHealth(name, service, state, fetchFn) {
  if (typeof fetchFn !== "function") {
    return { healthy: false, message: "health fetch is unavailable" };
  }
  const apiUrl = state.services.api?.url;
  const healthUrl =
    name === "api"
      ? `${service.url}/health`
      : name === "worker"
        ? `${apiUrl}/health/jobs?worker_id=${encodeURIComponent(service.workerId ?? "")}`
        : service.url;
  if (!healthUrl) {
    return { healthy: false, message: "health URL is missing" };
  }
  try {
    const response = await fetchFn(healthUrl, {
      signal: AbortSignal.timeout(1500),
    });
    if (!response.ok) {
      return {
        healthy: false,
        message: `health check returned HTTP ${response.status}`,
      };
    }
    if (name !== "worker") {
      return { healthy: true, message: "HTTP health check passed" };
    }
    const payload = await response.json();
    const matchingWorker = Array.isArray(payload.workers)
      ? payload.workers.find((worker) => worker.worker_id === service.workerId)
      : null;
    return matchingWorker?.healthy
      ? { healthy: true, message: "worker heartbeat is fresh" }
      : {
          healthy: false,
          message: "PID exists but the matching worker heartbeat is missing or stale",
        };
  } catch (error) {
    return {
      healthy: false,
      message: `health check failed: ${error.message}`,
    };
  }
}

async function main() {
  let args;
  try {
    args = parseArgs(process.argv.slice(2));
  } catch (error) {
    console.error(error.message);
    printHelp();
    process.exitCode = 1;
    return;
  }

  switch (args.command) {
    case "--version":
      console.log(VERSION);
      break;
    case undefined:
    case "--help":
      printHelp();
      break;
    case "init": {
      const workspacePath = resolveWorkspace(args.workspace);
      const workspace = ensureWorkspace(workspacePath, { force: args.force });
      console.log("ScholarFlow workspace initialized.");
      console.log(`Workspace: ${workspace.root}`);
      console.log(`Config: ${workspace.config}`);
      break;
    }
    case "start":
      await startServices(args);
      break;
    case "stop":
      await stopServices(args);
      break;
    case "status": {
      const workspacePath = resolveWorkspace(args.workspace);
      const workspace = getWorkspacePaths(workspacePath);
      const healthy = await printStatus(workspace, readState(workspace.state));
      if (!healthy) {
        process.exitCode = 1;
      }
      break;
    }
    default:
      console.error(`Unknown command: ${args.command}`);
      printHelp();
      process.exitCode = 1;
  }
}

const invokedPath = process.argv[1] ? path.resolve(process.argv[1]) : "";
const invokedRealPath =
  invokedPath && fs.existsSync(invokedPath) ? fs.realpathSync(invokedPath) : invokedPath;
if (invokedRealPath === fs.realpathSync(__filename)) {
  main().catch((error) => {
    console.error(error.message);
    process.exitCode = 1;
  });
}

export {
  deriveServiceStatus,
  getServiceStatusWith,
  printStatus,
  probeServiceHealth,
  startServices,
};
