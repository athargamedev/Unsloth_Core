import fs from "fs";
import crypto from "crypto";
import path from "path";
import { execSync, type ChildProcessWithoutNullStreams } from "child_process";
import type { Registry, Job, JobRegistrySnapshot } from "../types";
import { runningProcesses } from "./job-runner";

// ── Constants (injectable) ─────────────────────────────────────────────────

let PERSIST_DEBOUNCE_MS = 500;
let MAX_JOBS = 50;
let MAX_GLOBAL_LOG_LINES = 600;

export function configureRegistryLimits(opts: { persistDebounceMs?: number; maxJobs?: number; maxGlobalLogLines?: number }): void {
  if (opts.persistDebounceMs !== undefined) PERSIST_DEBOUNCE_MS = opts.persistDebounceMs;
  if (opts.maxJobs !== undefined) MAX_JOBS = opts.maxJobs;
  if (opts.maxGlobalLogLines !== undefined) MAX_GLOBAL_LOG_LINES = opts.maxGlobalLogLines;
}

// ── Persistence State ──────────────────────────────────────────────────────

let persistTimer: ReturnType<typeof setTimeout> | null = null;

// ── File Helpers ───────────────────────────────────────────────────────────

function ensureRuntime(runtimeDir: string): void {
  fs.mkdirSync(runtimeDir, { recursive: true });
}

function atomicWriteJSON(filePath: string, data: unknown): void {
  const tmpPath = filePath + ".tmp";
  fs.writeFileSync(tmpPath, JSON.stringify(data, null, 2), "utf8");
  fs.renameSync(tmpPath, filePath);
}

function appendServerLog(serverLogPath: string, line: string): void {
  const MAX_SERVER_LOG_BYTES = 512 * 1024;
  try {
    const runtimeDir = path.dirname(serverLogPath);
    fs.mkdirSync(runtimeDir, { recursive: true });
    const entry = `[${isoNow()}] ${line}\n`;
    fs.appendFileSync(serverLogPath, entry, "utf8");
    const stat = fs.statSync(serverLogPath);
    if (stat.size > MAX_SERVER_LOG_BYTES) {
      const rotated = path.join(path.dirname(serverLogPath), "server.log.1");
      fs.renameSync(serverLogPath, rotated);
    }
  } catch { /* best-effort */ }
}

function isoNow(): string {
  return new Date().toISOString();
}

// ── Registry API ───────────────────────────────────────────────────────────

export interface RegistryPaths {
  runtimeDir: string;
  registryPath: string;
  registryBakPath: string;
  logsDir: string;
  serverLogPath: string;
}

/**
 * Loads or creates the job registry from disk.
 */
export function loadRegistry(paths: RegistryPaths): Registry {
  const { runtimeDir, registryPath, registryBakPath, logsDir, serverLogPath } = paths;
  ensureRuntime(runtimeDir);
  fs.mkdirSync(logsDir, { recursive: true });

  const createDefault = (): Registry => ({
    executionMode: "local",
    jobs: [],
    logs: [],
    nodeId: crypto.randomUUID(),
    workflows: [],
    autoSyncExternal: true,
  });

  if (!fs.existsSync(registryPath)) {
    const reg = createDefault();
    atomicWriteJSON(registryPath, reg);
    appendServerLog(serverLogPath, "Fresh registry created");
    return reg;
  }

  try {
    const registry = JSON.parse(fs.readFileSync(registryPath, "utf8")) as Registry;
    registry.logs = [];

    // Stale job cleanup
    const staleRunning = registry.jobs.filter((j) => j.status === "running");
    for (const job of staleRunning) {
      job.status = "failed";
      job.exitCode = -1;
      job.finishedAt = isoNow();
      job.error = "Server restarted — job was still running";
    }
    if (staleRunning.length > 0) {
      globalLog(registry, `[STARTUP] Marked ${staleRunning.length} stale running job(s) as failed`);
    }

    // Job pruning
    if (registry.jobs.length > MAX_JOBS) {
      const excess = registry.jobs.length - MAX_JOBS;
      registry.jobs = registry.jobs.slice(excess);
      globalLog(registry, `[STARTUP] Pruned ${excess} old job(s), keeping ${registry.jobs.length}`);
    }

    if (registry.autoSyncExternal === undefined) registry.autoSyncExternal = true;
    if (!registry.nodeId) registry.nodeId = crypto.randomUUID();
    flushPersist(registry, paths);
    appendServerLog(serverLogPath, `Registry loaded: ${registry.jobs.length} jobs, ${registry.workflows.length} workflows`);
    return registry;
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    appendServerLog(serverLogPath, `Registry corrupt (${msg}), trying backup`);

    if (fs.existsSync(registryBakPath)) {
      try {
        const bak = JSON.parse(fs.readFileSync(registryBakPath, "utf8")) as Registry;
        bak.logs = [];
        bak.nodeId = crypto.randomUUID();
        if (!bak.workflows) bak.workflows = [];
        atomicWriteJSON(registryPath, bak);
        appendServerLog(serverLogPath, `Recovered from backup: ${bak.jobs.length} jobs`);
        return bak;
      } catch {
        appendServerLog(serverLogPath, "Backup also corrupt, starting fresh");
      }
    }

    const fresh = createDefault();
    atomicWriteJSON(registryPath, fresh);
    return fresh;
  }
}

/**
 * Backup the current registry file.
 */
export function backupRegistry(paths: RegistryPaths): void {
  try {
    fs.copyFileSync(paths.registryPath, paths.registryBakPath);
  } catch { /* best-effort */ }
}

/**
 * Debounced persist: schedules an atomic write after PERSIST_DEBOUNCE_MS.
 */
export function persistRegistry(registry: Registry, paths: RegistryPaths): void {
  ensureRuntime(paths.runtimeDir);
  if (persistTimer) clearTimeout(persistTimer);
  persistTimer = setTimeout(() => {
    backupRegistry(paths);
    atomicWriteJSON(paths.registryPath, registry);
    persistTimer = null;
  }, PERSIST_DEBOUNCE_MS);
}

/**
 * Immediate flush: cancels any pending debounce and writes synchronously.
 */
export function flushPersist(registry: Registry, paths: RegistryPaths): void {
  if (persistTimer) {
    clearTimeout(persistTimer);
    persistTimer = null;
  }
  ensureRuntime(paths.runtimeDir);
  backupRegistry(paths);
  atomicWriteJSON(paths.registryPath, registry);
}

/**
 * Add a timestamped line to the global registry log buffer.
 */
export function globalLog(registry: Registry, line: string): void {
  const timestampedLine = `[${isoNow()}] ${line}`;
  registry.logs.unshift(timestampedLine);
  registry.logs = registry.logs.slice(0, MAX_GLOBAL_LOG_LINES);
}

/**
 * Returns a snapshot of job registry state for API responses.
 */
export function getJobRegistrySnapshot(registry: Registry): JobRegistrySnapshot {
  return {
    jobs: registry.jobs,
    workflowCount: registry.workflows.length,
    autoSyncExternal: registry.autoSyncExternal !== false,
  };
}

// ── External Artifact Sync ─────────────────────────────────────────────────

function fileIso(filePath: string): string {
  try {
    return fs.statSync(filePath).mtime.toISOString();
  } catch {
    return isoNow();
  }
}

function defaultStages() {
  return [
    { name: "Dataset Prep", status: "pending" as const, logs: [] as string[] },
    { name: "Training", status: "pending" as const, logs: [] as string[] },
    { name: "Evaluation", status: "pending" as const, logs: [] as string[] },
    { name: "Export", status: "pending" as const, logs: [] as string[] },
    { name: "Feedback", status: "pending" as const, logs: [] as string[] },
  ];
}

function ensureExternalJob(
  registry: Registry,
  key: string,
  base: {
    name: string;
    type: string;
    commandId: string;
    npcKey?: string;
    createdAt: string;
    finishedAt: string;
    command: string[];
    loss?: number | null;
    progress?: number;
    logs?: string[];
  },
): boolean {
  const existing = registry.jobs.find((job) => job.id === key);
  if (existing) return false;

  const job: Job = {
    id: key,
    name: base.name,
    type: base.type,
    commandId: base.commandId,
    npcKey: base.npcKey,
    status: "completed",
    progress: base.progress ?? 100,
    loss: base.loss ?? null,
    createdAt: base.createdAt,
    startedAt: base.createdAt,
    finishedAt: base.finishedAt,
    command: base.command,
    stages: defaultStages(),
    logs: base.logs ?? ["[EXTERNAL] Imported from filesystem artifacts"],
    exitCode: 0,
    terminalReason: "external_import",
  };

  registry.jobs.unshift(job);
  return true;
}

/**
 * Scan the filesystem for external dataset, training, and export artifacts,
 * and add them to the registry as completed jobs.
 */
export function syncExternalArtifactsToRegistry(registry: Registry, repoRoot: string, paths: RegistryPaths): boolean {
  if (registry.autoSyncExternal === false) return false;
  let changed = false;

  // Datasets
  const datasetsRoot = path.join(repoRoot, "subjects", "datasets");
  if (fs.existsSync(datasetsRoot)) {
    for (const npcKey of fs.readdirSync(datasetsRoot)) {
      const npcDir = path.join(datasetsRoot, npcKey);
      if (!fs.statSync(npcDir).isDirectory()) continue;
      for (const technique of fs.readdirSync(npcDir)) {
        const techniqueDir = path.join(npcDir, technique);
        if (!fs.statSync(techniqueDir).isDirectory()) continue;
        const trainPath = path.join(techniqueDir, "train.jsonl");
        if (!fs.existsSync(trainPath)) continue;

        const key = `ext_dataset_${npcKey}_${technique}`;
        changed = ensureExternalJob(registry, key, {
          name: `External Dataset Generate (${npcKey}/${technique})`,
          type: "Dataset",
          commandId: "dataset-generate",
          npcKey,
          createdAt: fileIso(trainPath),
          finishedAt: fileIso(trainPath),
          command: ["./ucore", "generate", `subjects/${npcKey}.json`, "--technique", technique],
          logs: [`[EXTERNAL] dataset artifact detected: datasets/${npcKey}/${technique}/train.jsonl`],
        }) || changed;

        const cleanPath = path.join(techniqueDir, "train_clean.jsonl");
        if (fs.existsSync(cleanPath)) {
          const cleanKey = `ext_sanitize_${npcKey}_${technique}`;
          changed = ensureExternalJob(registry, cleanKey, {
            name: `External Dataset Sanitize (${npcKey}/${technique})`,
            type: "Dataset",
            commandId: "dataset-sanitize",
            npcKey,
            createdAt: fileIso(cleanPath),
            finishedAt: fileIso(cleanPath),
            command: ["./ucore", "sanitize", `subjects/datasets/${npcKey}/${technique}/train.jsonl`],
            logs: [`[EXTERNAL] sanitized dataset artifact detected: subjects/datasets/${npcKey}/${technique}/train_clean.jsonl`],
          }) || changed;
        }
      }
    }
  }

  // Training outputs
  const outputsRoot = path.join(repoRoot, "outputs");
  if (fs.existsSync(outputsRoot)) {
    for (const npcKey of fs.readdirSync(outputsRoot)) {
      const npcPath = path.join(outputsRoot, npcKey);
      if (!fs.statSync(npcPath).isDirectory()) continue;
      const runs = listNpcRunDirs(npcKey, repoRoot);
      for (const { runId, runDir } of runs) {
        const manifestCandidates = [
          path.join(runDir, "run_manifest.json"),
          path.join(runDir, "training_metrics.json"),
          path.join(runDir, "config_snapshot.yaml"),
          path.join(runDir, "adapter_config.json"),
        ];
        const manifestPath = manifestCandidates.find((candidate) => fs.existsSync(candidate));
        if (!manifestPath) continue;

        let createdAt = fileIso(manifestPath);
        let preset = "";
        let modelId = "";
        let loss: number | null = null;

        try {
          const raw = manifestPath.endsWith(".json")
            ? (JSON.parse(fs.readFileSync(manifestPath, "utf8")) as {
                created_at?: string;
                preset?: string;
                model_id?: string;
                results?: { training_loss?: number };
                train_loss?: number;
              })
            : {};
          if (raw.created_at) {
            const normalized = new Date(raw.created_at);
            if (!Number.isNaN(normalized.getTime())) createdAt = normalized.toISOString();
          }
          preset = raw.preset || "";
          modelId = raw.model_id || "";
          loss =
            typeof raw.results?.training_loss === "number"
              ? raw.results.training_loss
              : typeof raw.train_loss === "number"
                ? raw.train_loss
                : null;
        } catch {
          // ignore and use mtime
        }

        const key = `ext_train_${npcKey}_${runId}`;
        changed = ensureExternalJob(registry, key, {
          name: `External Train (${npcKey}/${runId}${preset ? ` • ${preset}` : ""}${modelId ? ` • ${path.basename(modelId)}` : ""})`,
          type: "Training",
          commandId: "train",
          npcKey,
          createdAt,
          finishedAt: fileIso(manifestPath),
          command: ["./ucore", "train", `subjects/${npcKey}.json`, "--from-spec", ...(preset ? ["--preset", preset] : [])],
          loss,
          logs: [`[EXTERNAL] run artifact detected: ${path.relative(repoRoot, manifestPath)}`],
        }) || changed;
      }
    }
  }

  // Exports
  const exportsRoot = path.join(repoRoot, "exports");
  if (fs.existsSync(exportsRoot)) {
    for (const npcKey of fs.readdirSync(exportsRoot)) {
      const npcDir = path.join(exportsRoot, npcKey);
      if (!fs.statSync(npcDir).isDirectory()) continue;
      for (const file of fs.readdirSync(npcDir).filter((f) => f.endsWith(".gguf"))) {
        const artifact = path.join(npcDir, file);
        const key = `ext_export_${npcKey}_${file}`;
        changed = ensureExternalJob(registry, key, {
          name: `External Export (${npcKey}/${file})`,
          type: "Export",
          commandId: "export",
          npcKey,
          createdAt: fileIso(artifact),
          finishedAt: fileIso(artifact),
          command: ["./ucore", "export", npcKey],
          logs: [`[EXTERNAL] GGUF artifact detected: exports/${npcKey}/${file}`],
        }) || changed;
      }
    }
  }

  if (changed) flushPersist(registry, paths);
  return changed;
}

/**
 * Scan running processes to discover ucore-related jobs that were started
 * outside the dashboard (e.g. from the command line).
 */
export function discoverActiveExternalProcesses(
  registry: Registry,
  repoRoot: string,
  paths: RegistryPaths,
): { changed: boolean; discovered: number } {
  if (registry.autoSyncExternal === false) return { changed: false, discovered: 0 };
  let changed = false;
  const now = isoNow();

  const trackedRunningPids = new Set<number>();
  for (const child of runningProcesses.values()) {
    if (typeof child.pid === "number" && Number.isFinite(child.pid)) trackedRunningPids.add(child.pid);
  }

  const trackedCombos = new Set<string>();
  for (const job of registry.jobs) {
    if (job.id.startsWith("ext_proc_") && job.status === "running") {
      trackedCombos.add(`${job.commandId ?? ""}|${job.npcKey ?? ""}`);
    }
  }

  const discoveredPids = new Set<number>();
  let psOutput = "";
  try {
    psOutput = execSync("ps -eo pid=,args=", { cwd: repoRoot, encoding: "utf8", timeout: 5000 });
  } catch {
    return { changed, discovered: 0 };
  }

  const lines = psOutput.split("\n").map((line) => line.trim()).filter(Boolean);
  for (const line of lines) {
    const match = line.match(/^(\d+)\s+(.+)$/);
    if (!match) continue;

    const pid = Number(match[1]);
    const args = match[2];
    if (!Number.isFinite(pid) || pid <= 0 || pid === process.pid) continue;
    if (trackedRunningPids.has(pid)) continue;

    const isRelevant =
      args.includes("./ucore ") ||
      args.includes("/ucore ") ||
      args.includes("scripts/training/train.py") ||
      args.includes("scripts/dataset/generate_dataset.py") ||
      args.includes("scripts/dataset/sanitize_dataset.py") ||
      args.includes("scripts/export/export.py") ||
      args.includes("scripts/evaluation/evaluate.py") ||
      args.includes("scripts/ops/smoke_test.py");
    if (!isRelevant) continue;
    if (args.includes("server.ts") || args.includes("vite") || args.includes("npm run dev")) continue;

    discoveredPids.add(pid);

    let commandId = "pipeline";
    let type = "Pipeline";
    if (args.includes(" generate ") || args.includes("generate-ollama") || args.includes("generate_dataset.py")) {
      commandId = "dataset-generate";
      type = "Dataset";
    } else if (args.includes(" sanitize ") || args.includes("sanitize_dataset.py")) {
      commandId = "dataset-sanitize";
      type = "Dataset";
    } else if (args.includes(" train ") || args.includes("train.py")) {
      commandId = "train";
      type = "Training";
    } else if (args.includes(" export ") || args.includes("export.py")) {
      commandId = "export";
      type = "Export";
    } else if (args.includes(" evaluate ") || args.includes("smoke_test") || args.includes("evaluate.py") || args.includes("smoke_test.py")) {
      commandId = "evaluate";
      type = "Evaluation";
    }

    const npcKey = extractNpcKeyFromArgs(args);
    const comboKey = `${commandId}|${npcKey ?? ""}`;
    if (trackedCombos.has(comboKey)) continue;
    trackedCombos.add(comboKey);

    const existingCombo = registry.jobs.find(
      (job) => job.id.startsWith("ext_proc_") && job.commandId === commandId && job.npcKey === npcKey && job.status === "running",
    );
    if (existingCombo) continue;

    const id = `ext_proc_${pid}`;
    const existing = registry.jobs.find((job) => job.id === id);
    if (existing) {
      let needsUpdate = false;
      if (existing.status !== "running") {
        existing.status = "running";
        existing.finishedAt = undefined;
        existing.exitCode = undefined;
        existing.terminalReason = "external_detected";
        needsUpdate = true;
      }
      if (existing.commandId !== commandId) {
        existing.commandId = commandId;
        needsUpdate = true;
      }
      if (existing.type !== type) {
        existing.type = type;
        needsUpdate = true;
      }
      if (existing.npcKey !== npcKey) {
        existing.npcKey = npcKey;
        needsUpdate = true;
      }
      if (needsUpdate) {
        changed = true;
      }
      continue;
    }

    const job: Job = {
      id,
      name: `External ${type} · PID ${pid}${npcKey ? ` · ${npcKey}` : ""}`,
      type,
      commandId,
      npcKey,
      status: "running",
      progress: 10,
      loss: null,
      createdAt: now,
      startedAt: now,
      command: ["external", args],
      stages: defaultStages(),
      logs: [`[EXTERNAL][PID ${pid}] discovered active process`, args],
      terminalReason: "external_detected",
    };
    registry.jobs.unshift(job);
    changed = true;
  }

  // Remove stale ext_proc entries
  for (const job of registry.jobs) {
    if (!job.id.startsWith("ext_proc_")) continue;
    if (job.status !== "running") continue;
    const pid = Number(job.id.replace("ext_proc_", ""));
    if (!Number.isFinite(pid) || discoveredPids.has(pid)) continue;

    job.status = "stopped";
    job.finishedAt = now;
    job.exitCode = -15;
    job.terminalReason = "external_process_not_found";
    changed = true;
  }

  if (changed) flushPersist(registry, paths);
  return { changed, discovered: discoveredPids.size };
}

// ── Internal Helpers ───────────────────────────────────────────────────────

function extractNpcKeyFromArgs(args: string): string | undefined {
  const match =
    args.match(/subjects\/NPC_specs\/([a-zA-Z0-9_\-]+)\.json/) ??
    args.match(/subjects\/([a-zA-Z0-9_\-]+)\.json/) ??
    args.match(/subjects\/datasets\/([a-zA-Z0-9_\-]+)\//) ??
    args.match(/outputs\/([a-zA-Z0-9_\-]+)\//) ??
    args.match(/exports\/([a-zA-Z0-9_\-]+)\//);
  return match?.[1];
}

function listNpcRunDirs(npcKey: string, repoRoot: string): Array<{ runId: string; runDir: string; layout: "canonical" | "legacy" }> {
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
