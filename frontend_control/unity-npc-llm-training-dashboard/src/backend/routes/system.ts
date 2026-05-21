import type { Express, Request, Response } from "express";
import path from "path";
import fs from "fs";
import os from "os";
import type { RouterDependencies } from "../types";
import { parseNvidiaSmiTelemetry, buildTelemetryPayload } from "../services/telemetry";
import { detectLocalModel } from "../services/model-detector";

// ── Simple TTL cache ───────────────────────────────────────────────────────

const ttlCache = new Map<string, { data: unknown; expires: number }>();
const LOCAL_MODEL_CACHE_TTL_MS = 2000;

async function withCache<T>(
  key: string,
  ttlMs: number,
  fetcher: () => Promise<T>,
): Promise<T> {
  const cached = ttlCache.get(key);
  if (cached && cached.expires > Date.now()) return cached.data as T;
  const data = await fetcher();
  ttlCache.set(key, {
    data,
    expires: Date.now() + Math.max(ttlMs, 500),
  });
  return data;
}

// ── Route registration ─────────────────────────────────────────────────────

/**
 * Registers /api/health, /api/telemetry, /api/docs, /api/system/status,
 * and misc REST endpoints (execution-mode, remote-config, suggestions, manifests, colab).
 */
export function registerRoutes(app: Express, deps: RouterDependencies): void {
  const { repoRoot, registry } = deps;

  // ── GET /api/health ─────────────────────────────────────────────────────
  app.get("/api/health", (_req: Request, res: Response) => {
    const coreChecks = {
      ucoreExists: fs.existsSync(path.join(repoRoot, "ucore")),
      subjectsDir: fs.existsSync(path.join(repoRoot, "subjects")),
      datasetsDir: fs.existsSync(path.join(repoRoot, "subjects", "datasets")),
      outputsDir: fs.existsSync(path.join(repoRoot, "outputs")),
      exportsDir: fs.existsSync(path.join(repoRoot, "exports")),
    };
    const supabaseChecks = {
      supabaseUrlConfigured: Boolean(process.env.SUPABASE_URL),
      supabaseKeyConfigured: Boolean(process.env.SUPABASE_KEY),
    };
    const ok = Object.values(coreChecks).every(Boolean);
    const statusCode = ok ? 200 : 503;
    res.status(statusCode).json({
      ok,
      checks: { ...coreChecks, ...supabaseChecks },
      executionMode: registry.executionMode,
      runningJobs: registry.jobs.filter((job) => job.status === "running").length,
      processId: process.pid,
      timestamp: new Date().toISOString(),
    });
  });

  // ── GET /api/telemetry ──────────────────────────────────────────────────
  app.get("/api/telemetry", (_req: Request, res: Response) => {
    res.json(buildTelemetryPayload(registry.nodeId));
  });

  // ── GET /api/docs ───────────────────────────────────────────────────────
  app.get("/api/docs", (_req: Request, res: Response) => {
    const docsRoot = path.join(repoRoot, "docs");
    const results: string[] = [];
    const walk = (dir: string) => {
      try {
        for (const entry of fs.readdirSync(dir)) {
          const full = path.join(dir, entry);
          const stat = fs.statSync(full);
          if (stat.isDirectory()) {
            walk(full);
          } else if (entry.endsWith(".md") || entry.endsWith(".pdf")) {
            results.push(path.relative(repoRoot, full));
          }
        }
      } catch {
        /* directory may not exist */
      }
    };
    if (fs.existsSync(docsRoot)) walk(docsRoot);
    const agentsMd = path.join(repoRoot, "AGENTS.md");
    if (fs.existsSync(agentsMd)) results.unshift("AGENTS.md");
    res.json(results);
  });

  // ── GET /api/system/status ──────────────────────────────────────────────
  app.get("/api/system/status", async (_req: Request, res: Response) => {
    const gpu = await withCache("gpuTelemetry", LOCAL_MODEL_CACHE_TTL_MS, async () =>
      parseNvidiaSmiTelemetry(),
    );
    const totalMem = os.totalmem();
    const freeMem = os.freemem();
    const cpuCount = Math.max(os.cpus().length, 1);
    res.json({
      executionMode: registry.executionMode,
      runningJobs: registry.jobs.filter((job) => job.status === "running").length,
      totalJobs: registry.jobs.length,
      repoRoot,
      localModel: await withCache("detectLocalModel", LOCAL_MODEL_CACHE_TTL_MS, detectLocalModel),
      gpu: gpu
        ? {
            name: gpu.gpuName,
            load: gpu.gpuLoad,
            temperature: gpu.gpuTemperature,
            vramUsed: gpu.gpuMemoryUsedGB,
            vramTotal: gpu.gpuMemoryTotalGB,
          }
        : null,
      cpu: {
        load: Math.round((os.loadavg()[0] / cpuCount) * 100),
        cores: cpuCount,
      },
      memory: {
        total: Math.round((totalMem / (1024 * 1024 * 1024)) * 10) / 10,
        used: Math.round(((totalMem - freeMem) / (1024 * 1024 * 1024)) * 10) / 10,
      },
      timestamp: new Date().toISOString(),
    });
  });

  // ── GET /api/execution-mode ─────────────────────────────────────────────
  app.get("/api/execution-mode", (_req: Request, res: Response) => {
    res.json({ mode: registry.executionMode });
  });

  // ── POST /api/execution-mode ────────────────────────────────────────────
  app.post("/api/execution-mode", (req: Request, res: Response) => {
    const mode = req.body?.mode;
    if (mode !== "local" && mode !== "remote") {
      res.status(400).json({ error: "Invalid mode." });
      return;
    }
    registry.executionMode = mode;
    res.json({ mode });
  });

  // ── GET /api/remote-config ──────────────────────────────────────────────
  app.get("/api/remote-config", (_req: Request, res: Response) => {
    res.json({
      configured: Boolean(process.env.REMOTE_API_URL && process.env.REMOTE_API_KEY),
      remoteUrl: process.env.REMOTE_API_URL || "",
      hasKey: Boolean(process.env.REMOTE_API_KEY),
      mode: registry.executionMode,
    });
  });

  // ── GET /api/suggestions ────────────────────────────────────────────────
  app.get("/api/suggestions", (_req: Request, res: Response) => {
    res.json({
      suggestions: [
        "Check Rank size for QuestGiver LoRA if loss plateau persists.",
        "Ensure dataset entries have consistent dialogue format.",
        "Verify Unity NPC protocol v4 compatibility in exports.",
        "Monitor GPU memory usage during training phases.",
        "Adjust temperature to 0.4 for better dialogue coherence.",
      ],
    });
  });

  // ── GET /api/manifests ──────────────────────────────────────────────────
  app.get("/api/manifests", (_req: Request, res: Response) => {
    const corporaRoot = path.join(repoRoot, "docs", "corpora");
    if (!fs.existsSync(corporaRoot)) {
      res.json([]);
      return;
    }
    try {
      const manifests = fs
        .readdirSync(corporaRoot)
        .filter((f) => f.endsWith(".json"))
        .map((file) => {
          const filePath = path.join(corporaRoot, file);
          let manifestData: Record<string, unknown> = {};
          try {
            manifestData = JSON.parse(
              fs.readFileSync(filePath, "utf8"),
            );
          } catch {
            // skip malformed
          }
          const sources = (
            (manifestData.sources as Array<{
              path: string;
              kind?: string;
              questions?: unknown[];
            }>) || []
          ).map((s) => ({
            ...s,
            path: s.path,
            questions: s.questions,
          }));
          return {
            name: file,
            path: `docs/corpora/${file}`,
            manifest_name:
              manifestData.manifest_name || file.replace(".json", ""),
            description: manifestData.description || "",
            version: manifestData.version || "",
            source_count: sources.length,
            lastModified: fs.statSync(filePath).mtime.toISOString(),
          };
        })
        .sort((a, b) => b.lastModified.localeCompare(a.lastModified));
      res.json(manifests);
    } catch (err) {
      res.status(500).json({ error: "Failed to list manifests" });
    }
  });

  // ── GET /api/manifests/:name ────────────────────────────────────────────
  app.get("/api/manifests/:name", (req: Request, res: Response) => {
    const name =
      String(req.params.name || "").replace(/\.json$/i, "") + ".json";
    const safePath = path.join(repoRoot, "docs", "corpora", name);
    if (
      !safePath.startsWith(path.join(repoRoot, "docs", "corpora"))
    ) {
      res.status(400).json({ error: "Invalid manifest name." });
      return;
    }
    if (!fs.existsSync(safePath)) {
      res
        .status(404)
        .json({ error: `Manifest not found: ${name}` });
      return;
    }
    try {
      const content = JSON.parse(
        fs.readFileSync(safePath, "utf8"),
      );
      const sources = (
        content.sources as Array<{
          path: string;
          kind?: string;
          questions?: unknown[];
        }>
      ).map((source) => {
        const sourcePath = path.join(repoRoot, source.path);
        const exists = fs.existsSync(sourcePath);
        return {
          ...source,
          exists,
          doc_size: exists
            ? `${Math.max(1, Math.round(fs.statSync(sourcePath).size / 1024))}KB`
            : "N/A",
        };
      });
      res.json({
        ...content,
        sources,
        manifest_path: `docs/corpora/${name}`,
      });
    } catch (err) {
      res
        .status(500)
        .json({ error: "Failed to load manifest" });
    }
  });

  // ── GET /api/colab/notebooks ────────────────────────────────────────────
  app.get("/api/colab/notebooks", (_req: Request, res: Response) => {
    const colabDir = path.join(repoRoot, "colab", "outputs");
    if (!fs.existsSync(colabDir)) {
      res.json([]);
      return;
    }
    try {
      const files = fs
        .readdirSync(colabDir)
        .filter((f) => f.endsWith(".ipynb"))
        .map((f) => {
          const filePath = path.join(colabDir, f);
          const stat = fs.statSync(filePath);
          let npcKey = "";
          let preset = "";
          try {
            const content = JSON.parse(
              fs.readFileSync(filePath, "utf8"),
            );
            const meta =
              content.metadata?.unsloth_core || {};
            npcKey = meta.npc_key || "";
            preset = meta.preset || "";
          } catch {
            // ignore
          }
          return {
            name: f,
            path: `colab/outputs/${f}`,
            npcKey,
            preset,
            size: `${Math.max(1, Math.round(stat.size / 1024))}KB`,
            lastModified: stat.mtime.toISOString(),
          };
        })
        .sort((a, b) =>
          b.lastModified.localeCompare(a.lastModified),
        );
      res.json(files);
    } catch (err) {
      res
        .status(500)
        .json({ error: "Failed to list Colab notebooks" });
    }
  });

  // ── GET /api/colab/download ─────────────────────────────────────────────
  app.get("/api/colab/download", (req: Request, res: Response) => {
    const requestedPath = String(req.query.path || "");
    if (
      !requestedPath.startsWith("colab/outputs/") ||
      requestedPath.includes("..")
    ) {
      res
        .status(400)
        .json({ error: "Invalid notebook path." });
      return;
    }
    const absolutePath = path.resolve(repoRoot, requestedPath);
    if (
      !fs.existsSync(absolutePath) ||
      !fs.statSync(absolutePath).isFile()
    ) {
      res
        .status(404)
        .json({ error: "Notebook file not found." });
      return;
    }
    res.download(absolutePath);
  });

  // ── GET /api/watch-logs ─────────────────────────────────────────────────
  app.get("/api/watch-logs", (_req: Request, res: Response) => {
    const watchLogsRoot = path.join(os.tmpdir(), "ucore-watch");
    const limit = 12;

    const listWatchRuns = () => {
      try {
        if (!fs.existsSync(watchLogsRoot)) return [];
        return fs
          .readdirSync(watchLogsRoot)
          .map((entry) => path.join(watchLogsRoot, entry))
          .filter(
            (entryPath) =>
              fs.existsSync(entryPath) &&
              fs.statSync(entryPath).isDirectory(),
          )
          .sort(
            (a, b) =>
              fs.statSync(b).mtimeMs - fs.statSync(a).mtimeMs,
          )
          .slice(0, limit)
          .map((watchDir) => {
            const summaryPath = path.join(watchDir, "summary.json");
            const alertsPath = path.join(watchDir, "alerts.jsonl");
            const streamPath = path.join(watchDir, "stream.log");
            const summary = readJsonFile<Record<string, unknown>>(
              summaryPath,
              {},
            );
            const alerts = readTailLines(alertsPath, 100)
              .map((line) => {
                try {
                  return JSON.parse(line) as {
                    timestamp?: string;
                    line?: string;
                    command?: string;
                  };
                } catch {
                  return null;
                }
              })
              .filter(Boolean) as Array<{
              timestamp: string;
              line: string;
              command: string;
            }>;
            return {
              watchDir,
              startedAt:
                typeof summary.started_at === "string"
                  ? summary.started_at
                  : null,
              finishedAt:
                typeof summary.finished_at === "string"
                  ? summary.finished_at
                  : null,
              returncode:
                typeof summary.returncode === "number"
                  ? summary.returncode
                  : null,
              command: Array.isArray(summary.command)
                ? summary.command.map((item) => String(item))
                : [],
              alerts,
              alertCount: alerts.length,
              streamTail: readTailLines(streamPath, 40),
            };
          });
      } catch {
        return [];
      }
    };

    const runs = listWatchRuns();
    const totalAlerts = runs.reduce(
      (sum, run) => sum + run.alertCount,
      0,
    );
    res.json({
      root: watchLogsRoot,
      totalAlerts,
      latestRun: runs[0] || null,
      runs,
    });
  });
}

function readJsonFile<T>(filePath: string, fallback: T): T {
  try {
    if (!fs.existsSync(filePath)) return fallback;
    return JSON.parse(fs.readFileSync(filePath, "utf8")) as T;
  } catch {
    return fallback;
  }
}

function readTailLines(
  filePath: string,
  maxLines = 40,
): string[] {
  try {
    if (!fs.existsSync(filePath)) return [];
    return fs
      .readFileSync(filePath, "utf8")
      .split("\n")
      .filter(Boolean)
      .slice(-maxLines);
  } catch {
    return [];
  }
}
