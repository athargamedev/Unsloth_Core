import fs from "fs";
import path from "path";
import type { DatasetInfo, RunInfo, ExportInfo } from "../types";

// ── Dataset Scanning ───────────────────────────────────────────────────────

/**
 * Scans subjects/datasets/ for all available datasets.
 */
export function scanDatasets(repoRoot: string): DatasetInfo[] {
  const datasetsRoot = path.join(repoRoot, "subjects", "datasets");
  if (!fs.existsSync(datasetsRoot)) return [];

  const results: DatasetInfo[] = [];

  for (const npcKey of fs.readdirSync(datasetsRoot)) {
    const npcPath = path.join(datasetsRoot, npcKey);
    if (!fs.statSync(npcPath).isDirectory()) continue;

    for (const technique of fs.readdirSync(npcPath)) {
      const techniqueDir = path.join(npcPath, technique);
      if (!fs.statSync(techniqueDir).isDirectory()) continue;

      const trainPath = path.join(techniqueDir, "train.jsonl");
      const entries = fs.existsSync(trainPath)
        ? fs.readFileSync(trainPath, "utf8").split("\n").filter(Boolean).length
        : 0;
      const stat = fs.existsSync(trainPath)
        ? fs.statSync(trainPath)
        : fs.statSync(techniqueDir);

      results.push({
        npcKey,
        technique,
        path: `subjects/datasets/${npcKey}/${technique}/train.jsonl`,
        entries,
        size: `${Math.max(1, Math.round(stat.size / 1024))}KB`,
        createdAt: stat.mtime.toISOString(),
      });
    }
  }

  return results;
}

// ── Run Scanning ───────────────────────────────────────────────────────────

function parseRunSnapshotScalar(raw: string): string | number | boolean | null {
  const value = raw.trim();
  if (!value || value === "null" || value === "~") return null;
  if (value === "true") return true;
  if (value === "false") return false;
  if (/^-?\d+(?:\.\d+)?(?:e[+-]?\d+)?$/i.test(value)) return Number(value);
  return value;
}

function readRunMetadata(runDir: string): Record<string, unknown> {
  const metadata: Record<string, unknown> = {
    hasConfigSnapshot: false,
    hasAdapter: fs.existsSync(path.join(runDir, "adapter_model.safetensors")),
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
        const match = trimmed.match(/^([A-Za-z0-9_]+):\s*(.*)$/);
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
      const metrics = JSON.parse(fs.readFileSync(metricsPath, "utf8")) as Record<string, unknown>;
      metadata.loss =
        typeof metrics.train_loss === "number"
          ? metrics.train_loss
          : typeof metrics.loss === "number"
            ? metrics.loss
            : null;
      metadata.trainRuntime =
        typeof metrics.train_runtime === "number" ? metrics.train_runtime : null;
      metadata.trainSamplesPerSecond =
        typeof metrics.train_samples_per_second === "number"
          ? metrics.train_samples_per_second
          : null;
      metadata.trainStepsPerSecond =
        typeof metrics.train_steps_per_second === "number"
          ? metrics.train_steps_per_second
          : null;
      metadata.epoch = typeof metrics.epoch === "number" ? metrics.epoch : null;
    } catch {
      // ignore malformed metrics
    }
  }

  // Scan for TensorBoard events
  const stack: string[] = [runDir];
  while (stack.length) {
    const current = stack.pop();
    if (!current || metadata.hasTensorBoard) continue;
    try {
      for (const entry of fs.readdirSync(current)) {
        const full = path.join(current, entry);
        const stat = fs.statSync(full);
        if (stat.isDirectory()) {
          stack.push(full);
        } else if (entry.startsWith("events.out.tfevents.")) {
          metadata.hasTensorBoard = true;
          break;
        }
      }
    } catch {
      // ignore unreadable directories
    }
  }

  return metadata;
}

function listNpcRunDirs(
  npcKey: string,
  repoRoot: string,
): Array<{ runId: string; runDir: string; layout: "canonical" | "legacy" }> {
  const npcOutputDir = path.join(repoRoot, "outputs", npcKey);
  const layouts = [
    { root: path.join(npcOutputDir, "runs"), layout: "canonical" as const },
    { root: npcOutputDir, layout: "legacy" as const },
  ];
  const runs: Array<{ runId: string; runDir: string; layout: "canonical" | "legacy" }> = [];

  for (const { root, layout } of layouts) {
    if (!fs.existsSync(root) || !fs.statSync(root).isDirectory()) continue;
    for (const runId of fs.readdirSync(root)) {
      if (!runId.startsWith("run_") && !/^\d{8}_/.test(runId)) continue;
      const runDir = path.join(root, runId);
      if (fs.statSync(runDir).isDirectory()) runs.push({ runId, runDir, layout });
    }
  }

  return runs;
}

/**
 * Scans outputs/ for all training runs.
 */
export function scanOutputs(repoRoot: string): RunInfo[] {
  const outputsRoot = path.join(repoRoot, "outputs");
  if (!fs.existsSync(outputsRoot)) return [];

  const entries: RunInfo[] = [];

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
        datasetPath: typeof metadata.dataset_path === "string" ? metadata.dataset_path : null,
        technique: typeof metadata.technique === "string" ? metadata.technique : null,
        loss: typeof metadata.loss === "number" ? metadata.loss : null,
        trainRuntime: typeof metadata.trainRuntime === "number" ? metadata.trainRuntime : null,
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
        loraRank: typeof metadata["lora.r"] === "number" ? metadata["lora.r"] : null,
        loraAlpha: typeof metadata["lora.alpha"] === "number" ? metadata["lora.alpha"] : null,
        wandbEnabled:
          typeof metadata["wandb.enabled"] === "boolean" ? metadata["wandb.enabled"] : null,
        hasConfigSnapshot: Boolean(metadata.hasConfigSnapshot),
        hasAdapter: Boolean(metadata.hasAdapter),
        hasTensorBoard: Boolean(metadata.hasTensorBoard),
      });
    }
  }

  return entries.sort((a, b) => b.updatedAt.localeCompare(a.updatedAt));
}

// ── Export Scanning ────────────────────────────────────────────────────────

/**
 * Scans exports/ for all exported GGUF files.
 */
export function scanExports(repoRoot: string): ExportInfo[] {
  const exportsRoot = path.join(repoRoot, "exports");
  if (!fs.existsSync(exportsRoot)) return [];

  const entries: ExportInfo[] = [];

  for (const npcKey of fs.readdirSync(exportsRoot)) {
    const npcDir = path.join(exportsRoot, npcKey);
    if (!fs.statSync(npcDir).isDirectory()) continue;

    for (const file of fs.readdirSync(npcDir).filter((f) => f.endsWith(".gguf"))) {
      const stat = fs.statSync(path.join(npcDir, file));
      entries.push({
        npcKey,
        file: `exports/${npcKey}/${file}`,
        updatedAt: stat.mtime.toISOString(),
      });
    }
  }

  return entries;
}
