import type { Express, Request, Response } from "express";
import path from "path";
import fs from "fs";
import type { RouterDependencies } from "../types";

/**
 * Registers /api/runs/* and /api/run/* and /api/tensorboard routes.
 */
export function registerRoutes(app: Express, deps: RouterDependencies): void {
  const { repoRoot, registry } = deps;

  // ── GET /api/runs ──────────────────────────────────────────────────────
  app.get("/api/runs", (_req: Request, res: Response) => {
    const outputsRoot = path.join(repoRoot, "outputs");
    if (!fs.existsSync(outputsRoot)) {
      res.json([]);
      return;
    }

    const entries: Array<Record<string, unknown>> = [];

    for (const npcKey of fs.readdirSync(outputsRoot)) {
      const npcPath = path.join(outputsRoot, npcKey);
      if (!fs.statSync(npcPath).isDirectory()) continue;

      for (const run of listNpcRunDirs(npcKey, repoRoot)) {
        const stat = fs.statSync(run.runDir);
        const metadata = readRunMetadata(run.runDir);

        entries.push({
          id: `${npcKey}/${run.runId}`,
          npcKey,
          runId: run.runId,
          path: path.relative(repoRoot, run.runDir),
          updatedAt: stat.mtime.toISOString(),
          layout: run.layout,
          model: typeof metadata.model === "string" ? metadata.model : null,
          datasetPath:
            typeof metadata.dataset_path === "string"
              ? metadata.dataset_path
              : null,
          technique:
            typeof metadata.technique === "string" ? metadata.technique : null,
          loss: typeof metadata.loss === "number" ? metadata.loss : null,
          trainRuntime:
            typeof metadata.trainRuntime === "number"
              ? metadata.trainRuntime
              : null,
          trainSamplesPerSecond:
            typeof metadata.trainSamplesPerSecond === "number"
              ? metadata.trainSamplesPerSecond
              : null,
          trainStepsPerSecond:
            typeof metadata.trainStepsPerSecond === "number"
              ? metadata.trainStepsPerSecond
              : null,
          epoch: typeof metadata.epoch === "number" ? metadata.epoch : null,
          batchSize:
            typeof metadata["training.batch_size"] === "number"
              ? metadata["training.batch_size"]
              : null,
          epochs:
            typeof metadata["training.num_epochs"] === "number"
              ? metadata["training.num_epochs"]
              : null,
          learningRate:
            typeof metadata["training.learning_rate"] === "number"
              ? metadata["training.learning_rate"]
              : null,
          loraRank:
            typeof metadata["lora.r"] === "number"
              ? metadata["lora.r"]
              : null,
          loraAlpha:
            typeof metadata["lora.alpha"] === "number"
              ? metadata["lora.alpha"]
              : null,
          wandbEnabled:
            typeof metadata["wandb.enabled"] === "boolean"
              ? metadata["wandb.enabled"]
              : null,
          hasConfigSnapshot: Boolean(metadata.hasConfigSnapshot),
          hasAdapter: Boolean(metadata.hasAdapter),
          hasTensorBoard: Boolean(metadata.hasTensorBoard),
        });
      }
    }

    entries.sort((a, b) =>
      String(b.updatedAt).localeCompare(String(a.updatedAt)),
    );
    res.json(entries);
  });

  // ── GET /api/run/:npcKey/:runId ──────────────────────────────────────
  app.get("/api/run/:npcKey/:runId", (req: Request, res: Response) => {
    const { npcKey, runId } = req.params;

    if (!/^[a-zA-Z0-9_-]+$/.test(npcKey)) {
      res.status(400).json({ error: "Invalid path" });
      return;
    }

    if (!safeRunId(runId)) {
      res.status(400).json({ error: "Invalid runId" });
      return;
    }

    const runPath =
      listNpcRunDirs(npcKey, repoRoot).find(
        (run) => run.runId === runId,
      )?.runDir || "";
    if (!fs.existsSync(runPath)) {
      res
        .status(404)
        .json({ error: `Run ${npcKey}/${runId} not found` });
      return;
    }

    let config: Record<string, unknown> = {};
    const configPath = path.join(runPath, "config.yaml");
    if (fs.existsSync(configPath)) {
      try {
        const raw = fs.readFileSync(configPath, "utf8");
        config = Object.fromEntries(
          raw
            .split("\n")
            .filter((l) => l.includes(":"))
            .map((l) => {
              const [k, ...v] = l.split(":");
              return [k.trim(), v.join(":").trim()];
            }),
        );
      } catch {
        /* ignore parse errors */
      }
    }

    let metrics: Record<string, unknown> = {};
    const metricsPath = path.join(runPath, "metrics.json");
    if (fs.existsSync(metricsPath)) {
      try {
        metrics = JSON.parse(fs.readFileSync(metricsPath, "utf8"));
      } catch {
        /* ignore parse errors */
      }
    }

    res.json({
      npcKey,
      runId,
      path: runPath,
      config,
      metrics,
    });
  });

  // ── GET /api/tensorboard ───────────────────────────────────────────
  app.get("/api/tensorboard", (req: Request, res: Response) => {
    const runId =
      typeof req.query.runId === "string" ? req.query.runId.trim() : "";
    const npcKey =
      typeof req.query.npcKey === "string" ? req.query.npcKey.trim() : "";

    if (!runId) {
      res.json({
        runId: "",
        scalars: {},
        error: "runId query parameter is required",
      });
      return;
    }

    let resolvedRun: { runId: string; runDir: string } | null = null;
    try {
      if (npcKey) {
        const run = listNpcRunDirs(npcKey, repoRoot).find(
          (item) => item.runId === runId,
        );
        resolvedRun = run
          ? { runId: run.runId, runDir: run.runDir }
          : null;
      } else {
        resolvedRun = findRunDirById(runId, repoRoot, registry);
      }
    } catch (error) {
      const msg =
        error instanceof Error ? error.message : "Invalid runId";
      res.json({ runId, scalars: {}, error: msg });
      return;
    }

    if (!resolvedRun) {
      res.json({
        runId,
        scalars: {},
        error: `Run directory not found for ${npcKey ? `${npcKey}/${runId}` : runId}`,
      });
      return;
    }

    try {
      const { execFileSync } = require("child_process");
      const result = execFileSync(
        "python",
        [
          "scripts/evaluation/tb_reader.py",
          "--run-dir",
          resolvedRun.runDir,
        ],
        { cwd: repoRoot, encoding: "utf8", timeout: 10000 },
      );
      const data = JSON.parse(result.trim());
      res.json(data);
    } catch (e) {
      const msg =
        e instanceof Error ? e.message : "Failed to read TensorBoard data";
      res.json({ runId, scalars: {}, error: msg });
    }
  });

  // ── GET /api/config/presets ───────────────────────────────────────
  app.get("/api/config/presets", (_req: Request, res: Response) => {
    res.json(listPresets(repoRoot));
  });

  // ── GET /api/presets ──────────────────────────────────────────────
  app.get("/api/presets", (_req: Request, res: Response) => {
    res.json(listPresets(repoRoot));
  });
}

// ── Helpers ────────────────────────────────────────────────────────────────

function listNpcRunDirs(
  npcKey: string,
  repoRoot: string,
): Array<{
  runId: string;
  runDir: string;
  layout: "canonical" | "legacy";
}> {
  const npcOutputDir = path.join(repoRoot, "outputs", npcKey);
  const layouts = [
    { root: path.join(npcOutputDir, "runs"), layout: "canonical" as const },
    { root: npcOutputDir, layout: "legacy" as const },
  ];
  const runs: Array<{
    runId: string;
    runDir: string;
    layout: "canonical" | "legacy";
  }> = [];

  for (const { root, layout } of layouts) {
    if (!fs.existsSync(root) || !fs.statSync(root).isDirectory()) continue;
    for (const runId of fs.readdirSync(root)) {
      if (!runId.startsWith("run_") && !/^\d{8}_/.test(runId)) continue;
      const runDir = path.join(root, runId);
      if (fs.statSync(runDir).isDirectory())
        runs.push({ runId, runDir, layout });
    }
  }

  return runs;
}

function readRunMetadata(
  runDir: string,
): Record<string, unknown> {
  const metadata: Record<string, unknown> = {
    hasConfigSnapshot: false,
    hasAdapter: fs.existsSync(
      path.join(runDir, "adapter_model.safetensors"),
    ),
    hasTensorBoard: false,
  };

  const configPath = path.join(runDir, "config_snapshot.yaml");
  if (fs.existsSync(configPath)) {
    metadata.hasConfigSnapshot = true;
    try {
      const raw = fs.readFileSync(configPath, "utf8");
      let section = "";
      for (const line of raw.split(/\r?\n/)) {
        if (!line.trim() || line.trim().startsWith("#")) continue;
        const indent = (line.match(/^\s*/) || [""])[0].length;
        const trimmed = line.trim();
        if (indent === 0 && trimmed.endsWith(":")) {
          section = trimmed.slice(0, -1);
          continue;
        }
        const match = trimmed.match(
          /^([A-Za-z0-9_]+):\s*(.*)$/,
        );
        if (!match) continue;
        const [, key, value] = match;
        const parsed = parseRunSnapshotScalar(value);
        if (indent === 0) {
          metadata[key] = parsed;
        } else if (section) {
          metadata[`${section}.${key}`] = parsed;
        }
      }
    } catch {
      // ignore malformed snapshots
    }
  }

  const metricsPath = path.join(runDir, "training_metrics.json");
  if (fs.existsSync(metricsPath)) {
    try {
      const metrics = JSON.parse(
        fs.readFileSync(metricsPath, "utf8"),
      ) as Record<string, unknown>;
      Object.assign(metadata, {
        loss:
          typeof metrics.train_loss === "number"
            ? metrics.train_loss
            : typeof metrics.loss === "number"
              ? metrics.loss
              : null,
        trainRuntime:
          typeof metrics.train_runtime === "number"
            ? metrics.train_runtime
            : null,
        trainSamplesPerSecond:
          typeof metrics.train_samples_per_second === "number"
            ? metrics.train_samples_per_second
            : null,
        trainStepsPerSecond:
          typeof metrics.train_steps_per_second === "number"
            ? metrics.train_steps_per_second
            : null,
        epoch: typeof metrics.epoch === "number" ? metrics.epoch : null,
      });
    } catch {
      // ignore malformed metrics
    }
  }

  return metadata;
}

function parseRunSnapshotScalar(
  raw: string,
): string | number | boolean | null {
  const value = raw.trim();
  if (!value || value === "null" || value === "~") return null;
  if (value === "true") return true;
  if (value === "false") return false;
  if (/^-?\d+(?:\.\d+)?(?:e[+-]?\d+)?$/i.test(value))
    return Number(value);
  return value;
}

function safeRunId(value: string): boolean {
  return /^run_[0-9]{3,}$|^[0-9]{8}_[a-zA-Z0-9_-]+_[0-9]{3,}$/.test(
    value,
  );
}

function findRunDirById(
  requestedId: string,
  repoRoot: string,
  registry: { jobs: Array<{ id: string; npcKey?: string; logs: string[]; createdAt: string; status: string }> },
): { runId: string; runDir: string } | null {
  const job = registry.jobs.find((item) => item.id === requestedId);
  const possibleRunIds = new Set<string>([requestedId]);

  if (job) {
    for (const line of job.logs) {
      const match = line.match(
        /outputs\/([a-zA-Z0-9_-]+)\/(?:runs\/)?([^/\s]+)(?:\/|\s|$)/,
      );
      if (match?.[2]) possibleRunIds.add(match[2]);
    }
    const outputLine = job.logs.find((line) =>
      line.includes("Output:"),
    );
    const outputMatch = outputLine?.match(
      /outputs\/([a-zA-Z0-9_-]+)\/(?:runs\/)?([^/\s]+)/,
    );
    if (outputMatch?.[2]) possibleRunIds.add(outputMatch[2]);
  }

  const npcKeys = job?.npcKey
    ? [job.npcKey]
    : fs.existsSync(path.join(repoRoot, "outputs"))
      ? fs.readdirSync(path.join(repoRoot, "outputs"))
      : [];
  for (const npcKey of npcKeys) {
    for (const run of listNpcRunDirs(npcKey, repoRoot)) {
      if (possibleRunIds.has(run.runId))
        return { runId: run.runId, runDir: run.runDir };
    }
  }

  // Fallback: running job, check latest run after job start
  if (job?.status === "running" && job.npcKey) {
    const jobCreatedMs =
      new Date(job.createdAt).getTime() || 0;
    const runs = listNpcRunDirs(job.npcKey, repoRoot)
      .filter(
        (run) => fs.statSync(run.runDir).mtimeMs >= jobCreatedMs,
      )
      .sort(
        (a, b) =>
          fs.statSync(b.runDir).mtimeMs -
          fs.statSync(a.runDir).mtimeMs,
      );
    if (runs.length > 0)
      return { runId: runs[0].runId, runDir: runs[0].runDir };
  }

  return null;
}

function listPresets(repoRoot: string): Array<{
  name: string;
  description: string;
}> {
  const presetsDir = path.join(repoRoot, "configs", "presets");
  const presets: Array<{ name: string; description: string }> = [];

  try {
    for (const file of fs.readdirSync(presetsDir)) {
      if (!(file.endsWith(".yaml") || file.endsWith(".yml"))) continue;
      const name = file.replace(/\.ya?ml$/, "");
      let description = "";
      try {
        const content = fs.readFileSync(
          path.join(presetsDir, file),
          "utf8",
        );
        const firstLine = content
          .split("\n")
          .find((l) => l.trim().startsWith("#"));
        if (firstLine)
          description = firstLine.replace(/^\s*#\s*/, "").trim();
      } catch {
        // ignore
      }
      presets.push({ name, description });
    }
  } catch {
    // presets dir may not exist
  }

  return presets.sort((a, b) => a.name.localeCompare(b.name));
}
