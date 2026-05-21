import "dotenv/config";
import express from "express";
import cors from "cors";
import rateLimit from "express-rate-limit";
import path from "path";
import fs from "fs";
import { createServer as createViteServer } from "vite";

import { createApp } from "./src/backend/index";
import {
  loadRegistry,
  persistRegistry,
  flushPersist,
  globalLog,
  backupRegistry,
  syncExternalArtifactsToRegistry,
  discoverActiveExternalProcesses,
  configureRegistryLimits,
  type RegistryPaths,
} from "./src/backend/services/registry";
import { buildCommandDefinitions } from "./src/backend/services/command-builder";
import {
  runningProcesses,
  terminalJobState,
  stopEscalationTimers,
  defaultStages,
  isoNow,
  makeId,
  launchJob,
  stopJob,
  type RunnerDeps,
} from "./src/backend/services/job-runner";
import { readJobLogs, writeJobLog } from "./src/backend/lib/read-job-logs";
import { JobQueue } from "./src/backend/services/job-queue";
import type { Registry, Job, RouterDependencies } from "./src/backend/types";

// ── Constants ───────────────────────────────────────────────────────────────

const PORT = parseInt(process.env.PORT || "3100", 10);
const isDev = process.env.NODE_ENV !== "production";

// ── Repo Root Discovery ─────────────────────────────────────────────────────

const dashboardRoot = process.cwd();
const serverDir = process.argv[1]
  ? path.dirname(path.resolve(process.argv[1]))
  : dashboardRoot;

function findRepoRoot(): string {
  const candidates = [
    process.env.UNSLOTH_CORE_ROOT,
    path.resolve(dashboardRoot, "../.."),
    path.resolve(serverDir, "../.."),
    path.resolve(serverDir, "../../.."),
  ].filter((candidate): candidate is string => Boolean(candidate));

  for (const candidate of candidates) {
    const resolved = path.resolve(candidate);
    if (fs.existsSync(path.join(resolved, "ucore"))) return resolved;
  }

  throw new Error(
    `Unable to locate Unsloth_Core root. Set UNSLOTH_CORE_ROOT or launch from the dashboard directory. Tried: ${candidates.join(", ")}`,
  );
}

const repoRoot = findRepoRoot();

// ── Registry Paths ──────────────────────────────────────────────────────────

const runtimeDir = path.join(dashboardRoot, ".runtime");
const paths: RegistryPaths = {
  runtimeDir,
  registryPath: path.join(runtimeDir, "registry.json"),
  registryBakPath: path.join(runtimeDir, "registry.json.bak"),
  logsDir: path.join(runtimeDir, "logs"),
  serverLogPath: path.join(runtimeDir, "server.log"),
};

configureRegistryLimits({ persistDebounceMs: 500, maxJobs: 50, maxGlobalLogLines: 600 });
const registry = loadRegistry(paths);

// ── Command Definitions ─────────────────────────────────────────────────────

const commandMap = new Map(
  buildCommandDefinitions(repoRoot).map((cmd) => [cmd.id, cmd]),
);

// ── Broadcast (no-op in modular — WS layer can be added later) ──────────────

const broadcast = (_type: string, _payload: unknown): void => {
  /* WebSocket broadcasting is handled by the monolithic server.ts */
};

// ── Cache Helpers ───────────────────────────────────────────────────────────

let jobsCacheTimestamp = 0;
const CACHE_TTL_MS = 2000;

const invalidateJobsCache = (): void => {
  jobsCacheTimestamp = 0;
};

const refreshJobsCache = (): void => {
  const now = Date.now();
  if (now - jobsCacheTimestamp < CACHE_TTL_MS) return;
  syncExternalArtifactsToRegistry(registry, repoRoot, paths);
  discoverActiveExternalProcesses(registry, repoRoot, paths);
  jobsCacheTimestamp = now;
};

// ── Persistence Wrappers ────────────────────────────────────────────────────

const persistRegistryWrapper = (reg: Registry): void => {
  persistRegistry(reg, paths);
};

const flushPersistWrapper = (reg: Registry): void => {
  flushPersist(reg, paths);
};

const globalLogWrapper = (reg: Registry, line: string): void => {
  globalLog(reg, line);
};

// ── Ollama GPU Memory Unloader ──────────────────────────────────────────────

const unloadGemmaModel = (): void => {
  try {
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const { execSync } = require("child_process") as typeof import("child_process");
    const result = execSync("ollama ps", {
      encoding: "utf8",
      timeout: 5000,
    });
    const lines = result.trim().split("\n");
    for (let i = 1; i < lines.length; i++) {
      const name = lines[i].trim().split(/\s+/)[0];
      if (!name) continue;
      try {
        execSync(`ollama stop ${name}`, { stdio: "ignore", timeout: 5000 });
        globalLogWrapper(registry, `[SYSTEM] Unloaded ${name} to free GPU memory`);
      } catch {
        /* model already stopped */
      }
    }
  } catch {
    /* no models running or ollama unavailable */
  }
};

// ── Background Sync ─────────────────────────────────────────────────────────

setInterval(() => {
  const changedArtifacts = syncExternalArtifactsToRegistry(registry, repoRoot, paths);
  const procResult = discoverActiveExternalProcesses(registry, repoRoot, paths);
  if (changedArtifacts || procResult.changed) {
    invalidateJobsCache();
  }
}, 3000).unref();

// ── Job Launcher / Stopper ──────────────────────────────────────────────────

const runnerDeps: RunnerDeps = {
  registry,
  repoRoot,
  broadcast,
  globalLog: globalLogWrapper,
  persistRegistry: persistRegistryWrapper,
  flushPersist: flushPersistWrapper,
  invalidateJobsCache,
  unloadGemmaModel,
  isoNow,
  makeId,
  defaultStages,
  writeJobLog,
};

const launchJobWrapper = (job: Job): Job => launchJob(job, runnerDeps);

// ── Router Dependencies ─────────────────────────────────────────────────────

const deps: RouterDependencies = {
  registry,
  runningProcesses,
  terminalJobState,
  stopEscalationTimers,
  broadcast,
  commandMap,
  repoRoot,
  invalidateJobsCache,
  persistRegistry: persistRegistryWrapper,
  flushPersist: flushPersistWrapper,
  globalLog: globalLogWrapper,
  defaultStages,
  isoNow,
  makeId,
  unloadGemmaModel,
  launchJob: launchJobWrapper,
  stopJob,
  readJobLogs,
};

// ── Main ────────────────────────────────────────────────────────────────────

async function main(): Promise<void> {
  const app = express();

  // ── Global Middleware ──────────────────────────────────────────────────

  // CORS
  app.use(
    cors({
      origin: isDev
        ? ["http://localhost:5173", "http://localhost:3100"]
        : "*",
      credentials: true,
    }),
  );

  // JSON body parser
  app.use(express.json({ limit: "10mb" }));

  // Rate limiting
  app.use(
    rateLimit({
      windowMs: 60_000,
      max: isDev ? 500 : 200,
      standardHeaders: true,
      legacyHeaders: false,
    }),
  );

  // Security headers (helmet-like)
  app.use((_req, res, next) => {
    res.setHeader("X-Content-Type-Options", "nosniff");
    res.setHeader("X-Frame-Options", "DENY");
    res.setHeader("X-XSS-Protection", "1; mode=block");
    res.setHeader("Referrer-Policy", "same-origin");
    res.setHeader(
      "Permissions-Policy",
      "camera=(), microphone=(), geolocation=()",
    );
    next();
  });

  // ── Health Check ──────────────────────────────────────────────────────

  app.get("/health", (_req, res) => {
    res.json({ status: "ok", timestamp: new Date().toISOString() });
  });

  // ── Mount Modular API Routes ──────────────────────────────────────────

  const apiApp = createApp(deps);
  app.use(apiApp);

  // ── Static Files (production) / Vite Dev Middleware (development) ──────

  if (!isDev) {
    const distPath = path.resolve(__dirname, "dist");
    app.use(express.static(distPath));
    app.get("*", (_req, res) => {
      res.sendFile(path.join(distPath, "index.html"));
    });
  } else {
    const vite = await createViteServer({
      server: { middlewareMode: true },
      appType: "spa",
    });
    app.use(vite.middlewares);
  }

  // ── Start Job Queue ───────────────────────────────────────────────────

  const queue = new JobQueue();
  await queue.init();
  queue.start();

  // ── Start HTTP Server ─────────────────────────────────────────────────

  const server = app.listen(PORT, () => {
    console.log(
      `[server-modular] Running on http://localhost:${PORT} (${isDev ? "development" : "production"})`,
    );
  });

  // ── Graceful Shutdown ─────────────────────────────────────────────────

  const shutdown = async (signal: string): Promise<void> => {
    console.log(
      `[server-modular] Received ${signal}, shutting down gracefully...`,
    );

    server.close(async () => {
      await queue.stop(10_000);
      process.exit(0);
    });

    // Force exit after 10 seconds
    setTimeout(() => {
      console.error("[server-modular] Forced exit after timeout");
      process.exit(1);
    }, 10_000);
  };

  process.on("SIGTERM", () => void shutdown("SIGTERM"));
  process.on("SIGINT", () => void shutdown("SIGINT"));

  // Periodically flush registry
  setInterval(() => {
    backupRegistry(paths);
  }, 300_000).unref();
}

main().catch((err) => {
  console.error("[server-modular] Failed to start:", err);
  process.exit(1);
});
