import "dotenv/config";
import express from "express";
import fs from "fs";
import os from "os";
import path from "path";
import crypto from "crypto";
import { execSync, spawn, type ChildProcessWithoutNullStreams } from "child_process";
import { createServer as createViteServer } from "vite";
import { WebSocketServer, WebSocket as WebSocketClient } from "ws";
import { computeProgressFromStages, deriveStageStatuses } from "./progressTruth";
import { CodeInterpreter } from "@e2b/code-interpreter";

type ExecutionMode = "local" | "remote";
type JobStatus = "pending" | "running" | "completed" | "failed" | "stopped";

interface Stage {
  name: string;
  status: "completed" | "running" | "pending" | "failed" | "stopped";
  logs: string[];
}

interface Job {
  id: string;
  name: string;
  type: string;
  commandId?: string;
  npcKey?: string;
  workflowId?: string;
  chainNext?: { commandId: string; payload: Record<string, unknown> };
  status: JobStatus;
  progress: number;
  loss: number | null;
  createdAt: string;
  startedAt?: string;
  finishedAt?: string;
  command: string[];
  stages: Stage[];
  logs: string[];
  exitCode?: number;
  stopRequested?: boolean;
  terminalReason?: string;
  wandbUrl?: string | null;
}

interface Registry {
  executionMode: ExecutionMode;
  jobs: Job[];
  logs: string[];
  nodeId: string;
  workflows: Workflow[];
}

interface StartCommandPayload {
  commandId?: string;
  type?: string;
  spec?: string;
  preset?: string;
  npcKey?: string;
  options?: Record<string, string | number | boolean | undefined>;
}

interface WorkflowStep {
  commandId: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  jobId?: string;
  payload: Record<string, unknown>;
}

interface Workflow {
  id: string;
  name: string;
  spec: string;
  steps: WorkflowStep[];
  currentStep: number;
  overallStatus: 'running' | 'completed' | 'failed';
  createdAt: string;
  finishedAt?: string;
}

const dashboardRoot = process.cwd();
const repoRoot = path.resolve(dashboardRoot, "../..");
const runtimeDir = path.join(dashboardRoot, ".runtime");
const registryPath = path.join(runtimeDir, "registry.json");

const MAX_LOG_LINES = 2000;
const MAX_GLOBAL_LOG_LINES = 600;
const PERSIST_DEBOUNCE_MS = 500;
let persistTimer: ReturnType<typeof setTimeout> | null = null;

const globalLog = (registry: Registry, line: string) => {
  const timestampedLine = `[${isoNow()}] ${line}`;
  registry.logs.unshift(timestampedLine);
  registry.logs = registry.logs.slice(0, MAX_GLOBAL_LOG_LINES);
};

const defaultStages = (): Stage[] => [
  { name: "Dataset Prep", status: "pending", logs: [] },
  { name: "Training", status: "pending", logs: [] },
  { name: "Evaluation", status: "pending", logs: [] },
  { name: "Export", status: "pending", logs: [] },
];

const ensureRuntime = () => fs.mkdirSync(runtimeDir, { recursive: true });
const loadRegistry = (): Registry => {
  ensureRuntime();
  if (!fs.existsSync(registryPath)) {
    const registry: Registry = { executionMode: "local", jobs: [], logs: [], nodeId: crypto.randomUUID(), workflows: [] };
    persistRegistry(registry);
    return registry;
  }

  try {
    const registry = JSON.parse(fs.readFileSync(registryPath, "utf8")) as Registry;
    registry.logs = []; // Global log buffer is transient — cleared on restart
    if (!registry.nodeId) {
      registry.nodeId = crypto.randomUUID();
      flushPersist(registry);
    }
    return registry;
  } catch {
    const registry: Registry = { executionMode: "local", jobs: [], logs: [], nodeId: crypto.randomUUID(), workflows: [] };
    flushPersist(registry);
    return registry;
  }
};

const persistRegistry = (registry: Registry) => {
  ensureRuntime();
  if (persistTimer) clearTimeout(persistTimer);
  persistTimer = setTimeout(() => {
    fs.writeFileSync(registryPath, JSON.stringify(registry, null, 2), "utf8");
    persistTimer = null;
  }, PERSIST_DEBOUNCE_MS);
};

const flushPersist = (registry: Registry) => {
  if (persistTimer) {
    clearTimeout(persistTimer);
    persistTimer = null;
  }
  ensureRuntime();
  fs.writeFileSync(registryPath, JSON.stringify(registry, null, 2), "utf8");
};

const isoNow = () => new Date().toISOString();
const makeId = () => `job_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`;

type CommandDefinition = {
  id: string;
  label: string;
  icon: string;
  color: "accent" | "success" | "warning" | "danger" | "default";
  type: string;
  requiredFields: string[];
  build: (payload: StartCommandPayload) => string[];
};

const sanitizeToken = (value: string, fieldName: string): string => {
  if (!value || !/^[a-zA-Z0-9_./:-]+$/.test(value)) {
    throw new Error(`Invalid ${fieldName}.`);
  }
  return value;
};

const normalizeRelativePath = (value: string, fieldName: string): string => {
  const token = sanitizeToken(value, fieldName);
  return token.replace(/^\.{1,2}\//, "");
};

const canonicalizeExistingPath = (targetPath: string): string => {
  return fs.realpathSync(targetPath);
};

const canonicalizePathFromNearestExistingParent = (targetPath: string): string => {
  if (fs.existsSync(targetPath)) {
    return canonicalizeExistingPath(targetPath);
  }

  const segments: string[] = [];
  let currentPath = path.resolve(targetPath);
  while (!fs.existsSync(currentPath)) {
    const parentPath = path.dirname(currentPath);
    if (parentPath === currentPath) {
      throw new Error("Invalid path: no existing parent for canonicalization.");
    }
    segments.unshift(path.basename(currentPath));
    currentPath = parentPath;
  }

  const canonicalParent = canonicalizeExistingPath(currentPath);
  return path.resolve(canonicalParent, ...segments);
};

const isPathWithinOrEqualToRoot = (candidate: string, allowedRoot: string): boolean => {
  const relative = path.relative(allowedRoot, candidate);
  return relative === "" || (!relative.startsWith("..") && !path.isAbsolute(relative));
};

const resolvePathWithinRoots = (
  inputPath: string,
  fieldName: string,
  allowedRoots: string[],
): string => {
  const safeInput = normalizeRelativePath(inputPath, fieldName);
  const absoluteCandidate = path.resolve(repoRoot, safeInput);

  const canonicalAllowedRoots = allowedRoots.map((root) => {
    const absoluteRoot = path.resolve(root);
    if (!fs.existsSync(absoluteRoot)) {
      throw new Error(`Invalid ${fieldName}: allowed root is unavailable.`);
    }
    return canonicalizeExistingPath(absoluteRoot);
  });

  const canonicalCandidate = canonicalizePathFromNearestExistingParent(absoluteCandidate);
  const isAllowed = canonicalAllowedRoots.some((canonicalRoot) => {
    return isPathWithinOrEqualToRoot(canonicalCandidate, canonicalRoot);
  });

  if (!isAllowed) {
    throw new Error(`Invalid ${fieldName}: path escapes allowed roots.`);
  }

  const canonicalRepoRoot = canonicalizeExistingPath(repoRoot);
  return path.relative(canonicalRepoRoot, canonicalCandidate);
};

const readNetworkTotals = () => {
  try {
    const procNet = fs.readFileSync('/proc/net/dev', 'utf8');
    return procNet
      .split('\n')
      .slice(2)
      .map((line) => line.trim())
      .filter(Boolean)
      .reduce(
        (acc, line) => {
          const parts = line.split(/\s+/);
          if (parts.length < 17) return acc;
          const iface = parts[0].replace(':', '');
          if (iface === 'lo') return acc;
          acc.rx += Number(parts[1]) || 0;
          acc.tx += Number(parts[9]) || 0;
          return acc;
        },
        { rx: 0, tx: 0 },
      );
  } catch {
    return { rx: 0, tx: 0 };
  }
};

let previousNetworkSample = {
  rx: 0,
  tx: 0,
  timestamp: 0,
};

const parseNvidiaSmiTelemetry = () => {
  try {
    const output = execSync(
      'nvidia-smi --query-gpu=name,utilization.gpu,memory.total,memory.used,temperature.gpu --format=csv,noheader,nounits',
      { encoding: 'utf8', timeout: 5000 },
    ).trim();

    if (!output) return null;
    const firstLine = output.split('\n')[0].trim();
    const [name, util, memoryTotal, memoryUsed, temperature] = firstLine.split(',').map((value) => value.trim());

    return {
      gpuName: name || 'GPU',
      gpuLoad: Number(util) || 0,
      gpuMemoryTotalGB: Math.round((Number(memoryTotal) / 1024) * 10) / 10,
      gpuMemoryUsedGB: Math.round((Number(memoryUsed) / 1024) * 10) / 10,
      gpuTemperature: Number(temperature) || 0,
    };
  } catch {
    return null;
  }
};

const buildTelemetryPayload = (nodeId: string) => {
  const gpuTelemetry = parseNvidiaSmiTelemetry();
  const totalMemory = os.totalmem();
  const freeMemory = os.freemem();
  const usedMemoryBytes = totalMemory - freeMemory;
  const cpuCount = Math.max(os.cpus().length, 1);
  const cpuLoad = Math.round((os.loadavg()[0] / cpuCount) * 100);
  const networkTotals = readNetworkTotals();
  const now = Date.now();
  let rxMBps = 0;
  let txMBps = 0;

  if (previousNetworkSample.timestamp > 0) {
    const elapsedSeconds = Math.max((now - previousNetworkSample.timestamp) / 1000, 0.5);
    rxMBps = Math.max(0, (networkTotals.rx - previousNetworkSample.rx) / elapsedSeconds / 1024 / 1024);
    txMBps = Math.max(0, (networkTotals.tx - previousNetworkSample.tx) / elapsedSeconds / 1024 / 1024);
  }

  previousNetworkSample = {
    rx: networkTotals.rx,
    tx: networkTotals.tx,
    timestamp: now,
  };

  return {
    gpuLoad: gpuTelemetry?.gpuLoad ?? 0,
    gpuTemperature: gpuTelemetry?.gpuTemperature ?? 0,
    gpuMemoryUsedGB: gpuTelemetry?.gpuMemoryUsedGB ?? 0,
    gpuMemoryTotalGB: gpuTelemetry?.gpuMemoryTotalGB ?? 0,
    gpuName: gpuTelemetry?.gpuName ?? 'GPU',
    cpuLoad: Math.max(0, Math.min(cpuLoad, 999)),
    memoryUsedGB: Math.round((usedMemoryBytes / 1024 / 1024 / 1024) * 10) / 10,
    memoryTotalGB: Math.round((totalMemory / 1024 / 1024 / 1024) * 10) / 10,
    platform: os.platform(),
    nodeVersion: process.version,
    nodeId,
    timestamp: isoNow(),
    networkRxMBps: Math.round(rxMBps * 10) / 10,
    networkTxMBps: Math.round(txMBps * 10) / 10,
  };
};

const requireString = (value: unknown, fieldName: string): string => {
  if (typeof value !== "string" || value.trim() === "") {
    throw new Error(`${fieldName} is required.`);
  }
  return value.trim();
};

const optionValue = (payload: StartCommandPayload, key: string): string => {
  const raw = payload.options?.[key];
  if (typeof raw === "string") return raw;
  if (typeof raw === "number" || typeof raw === "boolean") return String(raw);
  return "";
};

const parsedSpec = (payload: StartCommandPayload): string => {
  const spec = requireString(payload.spec, "spec");
  return resolvePathWithinRoots(spec, "spec", [path.join(repoRoot, "subjects")]);
};

const parsedDatasetPath = (payload: StartCommandPayload): string => {
  return resolvePathWithinRoots(
    requireString(optionValue(payload, "datasetPath"), "datasetPath"),
    "datasetPath",
    [path.join(repoRoot, "datasets")],
  );
};

const parsedModelPath = (payload: StartCommandPayload): string => {
  return resolvePathWithinRoots(
    requireString(optionValue(payload, "modelPath"), "modelPath"),
    "modelPath",
    [path.join(repoRoot, "exports"), path.join(repoRoot, "outputs")],
  );
};

const parsedBaseline = (payload: StartCommandPayload): string => {
  return resolvePathWithinRoots(
    requireString(optionValue(payload, "baseline"), "baseline"),
    "baseline",
    [path.join(repoRoot, "exports"), path.join(repoRoot, "outputs")],
  );
};

const parsedCandidate = (payload: StartCommandPayload): string => {
  return resolvePathWithinRoots(
    requireString(optionValue(payload, "candidate"), "candidate"),
    "candidate",
    [path.join(repoRoot, "exports"), path.join(repoRoot, "outputs")],
  );
};

const parsedValData = (payload: StartCommandPayload): string => {
  return resolvePathWithinRoots(
    requireString(optionValue(payload, "valData"), "valData"),
    "valData",
    [path.join(repoRoot, "datasets")],
  );
};


const commandDefinitions: CommandDefinition[] = [
  {
    id: "dataset-generate",
    label: "Generate Dataset",
    icon: "database",
    color: "accent",
    type: "Dataset",
    requiredFields: ["spec"],
    build: (payload) => {
      const args = ["./ucore", "generate", parsedSpec(payload)];
      const technique = String(optionValue(payload, "technique") || "").trim();
      const model = String(optionValue(payload, "model") || "").trim();
      if (technique) args.push("--technique", sanitizeToken(technique, "technique"));
      if (model) args.push("--model", sanitizeToken(model, "model"));
      if (technique === "ollama") args.push("--ollama");
      return args;
    },
  },
  {
    id: "dataset-sanitize",
    label: "Sanitize Dataset",
    icon: "shield",
    color: "warning",
    type: "Dataset",
    requiredFields: ["options.datasetPath"],
    build: (payload) => ["./ucore", "sanitize", parsedDatasetPath(payload)],
  },
  { id: "train", label: "Train LoRA", icon: "zap", color: "accent", type: "Training", build: (payload) => {
      const args = [
        "./ucore",
        "train",
        resolvePathWithinRoots(requireString(payload.spec, "spec"), "spec", [path.join(repoRoot, "subjects")]),
        "--from-spec",
      ];
      const preset = String(payload.preset || "").trim();
      if (preset) args.push("--preset", sanitizeToken(preset, "preset"));
      // Hyperparams from options
      const opts = payload.options || {};
      if (opts.wandb === true || opts.wandb === "true") args.push("--wandb");
      if (opts.learningRate) args.push("--lr", String(opts.learningRate));
      if (opts.batchSize) args.push("--batch-size", String(opts.batchSize));
      if (opts.epochs) args.push("--epochs", String(opts.epochs));
      if (opts.rank) args.push("--lora-r", String(opts.rank));
      if (opts.alpha) args.push("--lora-alpha", String(opts.alpha));
      if (opts.scheduler && ["cosine", "linear", "constant"].includes(String(opts.scheduler))) args.push("--lr-scheduler", String(opts.scheduler));
      return args;
    }, requiredFields: ["spec"] },
  {
    id: "pipeline",
    label: "Run Full Pipeline",
    icon: "layers",
    color: "success",
    type: "Pipeline",
    requiredFields: ["spec"],
    build: (payload) => {
      const cmd = ["./ucore", "pipeline", parsedSpec(payload)];
      const preset = String(payload.preset || "").trim();
      const technique = String(optionValue(payload, "technique") || "").trim();
      const notebooklmInput = String(optionValue(payload, "notebooklmInput") || "").trim();
      const track = String(optionValue(payload, "track") || "").trim().toLowerCase();
      const wandb = String(optionValue(payload, "wandb") || "").trim().toLowerCase();
      if (preset) cmd.push("--preset", sanitizeToken(preset, "preset"));
      if (technique) cmd.push("--technique", sanitizeToken(technique, "technique"));
      if (notebooklmInput) cmd.push("--notebooklm-input", normalizeRelativePath(notebooklmInput, "notebooklmInput"));
      if (track === "true" || track === "1") cmd.push("--track");
      if (wandb === "true" || wandb === "1") cmd.push("--wandb");
      return cmd;
    },
  },
  {
    id: "export",
    label: "Export GGUF",
    icon: "external-link",
    color: "success",
    type: "Export",
    requiredFields: ["npcKey", "options.modelId"],
    build: ({ npcKey, options }) => ["./ucore", "export", sanitizeToken(requireString(npcKey, "npcKey"), "npcKey"), "--model", sanitizeToken(requireString(String(options?.modelId || ""), "modelId"), "modelId")],
  },
  {
    id: "export-adapter",
    label: "Export Adapter",
    icon: "external-link",
    color: "default",
    type: "Export",
    requiredFields: ["npcKey"],
    build: ({ npcKey }) => ["./ucore", "export-adapter", `outputs/${sanitizeToken(requireString(npcKey, "npcKey"), "npcKey")}/`],
  },
  {
    id: "evaluate",
    label: "Evaluate Candidate",
    icon: "bar-chart",
    color: "accent",
    type: "Evaluation",
    requiredFields: ["options.baseline", "options.candidate", "spec"],
    build: (payload) => {
      const valData = optionValue(payload, "valData");
      const command = ["./ucore", "evaluate", "--baseline", parsedBaseline(payload), "--candidate", parsedCandidate(payload), "--spec", parsedSpec(payload)];
      if (valData.trim()) command.push("--val-data", parsedValData(payload));
      return command;
    },
  },
  {
    id: "smoke",
    label: "Smoke Test",
    icon: "activity",
    color: "warning",
    type: "Validation",
    requiredFields: ["options.modelPath", "spec"],
    build: (payload) => ["./ucore", "smoke", parsedModelPath(payload), "--spec", parsedSpec(payload)],
  },
  {
    id: "deploy",
    label: "Deploy Package",
    icon: "external-link",
    color: "success",
    type: "Deploy",
    requiredFields: ["options.npcKey", "options.modelId"],
    build: ({ options }) => ["python", "scripts/export.py", sanitizeToken(requireString(String(options?.npcKey || ""), "npcKey"), "npcKey"), "--model", sanitizeToken(requireString(String(options?.modelId || ""), "modelId"), "modelId")],
  },
  {
    id: "supabase-check",
    label: "Supabase Health Check",
    icon: "shield",
    color: "default",
    type: "System",
    requiredFields: ["npcKey"],
    build: ({ npcKey, options }) => {
      const args = ["./ucore", "supabase-check", "--npc-key", sanitizeToken(requireString(npcKey, "npcKey"), "npcKey")];
      const playerId = String(options?.playerId || "").trim();
      if (playerId) args.push("--player-id", sanitizeToken(playerId, "playerId"));
      return args;
    },
  },
];

const commandMap = new Map(commandDefinitions.map((cmd) => [cmd.id, cmd]));

const runningProcesses = new Map<string, ChildProcessWithoutNullStreams>();
const terminalJobState = new Map<string, { stopRequested: boolean; terminal: boolean }>();
const stopEscalationTimers = new Map<string, NodeJS.Timeout>();
const STOP_ESCALATION_MS = 10_000;

const parseLoss = (line: string): number | null => {
  const match = line.match(/loss[:=]\s*([0-9]*\.?[0-9]+)/i);
  if (!match) return null;
  return Number(match[1]);
};

const commandStageIndex = (job: Job): number => {
  switch (job.commandId) {
    case "dataset-generate":
    case "dataset-sanitize":
      return 0;
    case "train":
      return 1;
    case "evaluate":
    case "smoke":
      return 2;
    case "export":
    case "export-adapter":
    case "deploy":
      return 3;
    case "pipeline":
      return 0;
    default:
      return 0;
  }
};

const syncPipelineStageFromLogs = (job: Job): number => {
  for (let i = job.logs.length - 1; i >= 0; i -= 1) {
    const line = job.logs[i].toLowerCase();
    const marker = line.match(/\[stage\]\s+(dataset|training|evaluation|export|complete)/i);
    if (!marker) continue;
    const stage = marker[1];
    if (stage === "dataset") return 0;
    if (stage === "training") return 1;
    if (stage === "evaluation") return 2;
    if (stage === "export" || stage === "complete") return 3;
  }
  return 0;
};

const syncExportStageFromStatusFile = (job: Job) => {
  if (!job.npcKey) return;
  const statusPath = path.join(repoRoot, "exports", job.npcKey, "export_status.json");
  if (!fs.existsSync(statusPath)) return;
  try {
    const raw = JSON.parse(fs.readFileSync(statusPath, "utf8")) as { state?: string; substep?: string };
    if (raw.substep) {
      const stage = job.stages[3];
      if (stage) {
        const line = `[STATUS][export] substep=${raw.substep} state=${raw.state || "unknown"}`;
        if (stage.logs[stage.logs.length - 1] !== line) {
          stage.logs.push(line);
          stage.logs = stage.logs.slice(-50);
        }
      }
    }
  } catch {
    // ignore malformed status artifact
  }
};

const updateStagesFromTruth = (job: Job) => {
  const activeIndex = job.commandId === "pipeline" ? syncPipelineStageFromLogs(job) : commandStageIndex(job);

  job.stages = deriveStageStatuses(job.stages, job.status, activeIndex, job.commandId === "pipeline");

  if (activeIndex === 3) {
    syncExportStageFromStatusFile(job);
  }

  job.progress = computeProgressFromStages(job.status, job.stages);
};

const appendStageLog = (job: Job, message: string) => {
  const activeIndex = job.commandId === "pipeline" ? syncPipelineStageFromLogs(job) : commandStageIndex(job);
  const stage = job.stages[activeIndex] ?? job.stages[job.stages.length - 1];
  if (!stage) return;
  stage.logs.push(message);
  stage.logs = stage.logs.slice(-50);
};

const reconcileOrphanedJobs = (registry: Registry) => {
  let changed = false;
  const now = isoNow();
  for (const job of registry.jobs) {
    if (job.status !== "running" && job.status !== "pending") continue;
    job.status = "failed";
    job.terminalReason = "server_restarted";
    job.finishedAt = job.finishedAt ?? now;
    job.exitCode = typeof job.exitCode === "number" ? job.exitCode : -1;
    appendStageLog(job, "[SYSTEM] Marked failed: server restarted before completion.");
    globalLog(registry, `[SYSTEM] reconciled ${job.id} to failed (server_restarted)`);
    changed = true;
  }
  if (changed) flushPersist(registry);
};

const fileIso = (filePath: string): string => {
  try {
    return fs.statSync(filePath).mtime.toISOString();
  } catch {
    return isoNow();
  }
};

const ensureExternalJob = (
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
) => {
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

  updateStagesFromTruth(job);
  registry.jobs.unshift(job);
  globalLog(registry, `[SYNC] imported external job ${job.id}`);
  return true;
};

const syncExternalArtifactsToRegistry = (registry: Registry) => {
  let changed = false;

  const datasetsRoot = path.join(repoRoot, "datasets");
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
            command: ["./ucore", "sanitize", `datasets/${npcKey}/${technique}/train.jsonl`],
            logs: [`[EXTERNAL] sanitized dataset artifact detected: datasets/${npcKey}/${technique}/train_clean.jsonl`],
          }) || changed;
        }
      }
    }
  }

  const outputsRoot = path.join(repoRoot, "outputs");
  if (fs.existsSync(outputsRoot)) {
    for (const npcKey of fs.readdirSync(outputsRoot)) {
      const runsDir = path.join(outputsRoot, npcKey, "runs");
      if (!fs.existsSync(runsDir) || !fs.statSync(runsDir).isDirectory()) continue;

      for (const runId of fs.readdirSync(runsDir)) {
        const runDir = path.join(runsDir, runId);
        if (!fs.statSync(runDir).isDirectory()) continue;
        const manifestPath = path.join(runDir, "run_manifest.json");
        if (!fs.existsSync(manifestPath)) continue;

        let createdAt = fileIso(manifestPath);
        let preset = "";
        let modelId = "";
        let loss: number | null = null;

        try {
          const raw = JSON.parse(fs.readFileSync(manifestPath, "utf8")) as {
            created_at?: string;
            preset?: string;
            model_id?: string;
            results?: { training_loss?: number };
          };
          if (raw.created_at) {
            const normalized = new Date(raw.created_at);
            if (!Number.isNaN(normalized.getTime())) createdAt = normalized.toISOString();
          }
          preset = raw.preset || "";
          modelId = raw.model_id || "";
          loss = typeof raw.results?.training_loss === "number" ? raw.results.training_loss : null;
        } catch {
          // ignore malformed manifests and still import by file mtime
        }

        const key = `ext_train_${npcKey}_${runId}`;
        changed = ensureExternalJob(registry, key, {
          name: `External Train (${npcKey}/${runId})`,
          type: "Training",
          commandId: "train",
          npcKey,
          createdAt,
          finishedAt: fileIso(manifestPath),
          command: ["./ucore", "train", `subjects/${npcKey}.json`, "--from-spec", ...(preset ? ["--preset", preset] : [])],
          loss,
          logs: [
            `[EXTERNAL] run manifest detected: outputs/${npcKey}/runs/${runId}/run_manifest.json`,
            ...(modelId ? [`[EXTERNAL] model=${modelId}`] : []),
          ],
        }) || changed;
      }
    }
  }

  const exportsRoot = path.join(repoRoot, "exports");
  if (fs.existsSync(exportsRoot)) {
    for (const npcKey of fs.readdirSync(exportsRoot)) {
      const npcDir = path.join(exportsRoot, npcKey);
      if (!fs.statSync(npcDir).isDirectory()) continue;
      for (const file of fs.readdirSync(npcDir)) {
        if (!file.endsWith(".gguf")) continue;
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

  if (changed) flushPersist(registry);
  return changed;
};

const discoverActiveExternalProcesses = (registry: Registry) => {
  let changed = false;
  const now = isoNow();

  const trackedRunningPids = new Set<number>();
  for (const child of runningProcesses.values()) {
    if (typeof child.pid === "number" && Number.isFinite(child.pid)) trackedRunningPids.add(child.pid);
  }

  // Build a set of (commandId,npcKey) pairs already tracked as running ext_proc jobs
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
      args.includes("scripts/train.py") ||
      args.includes("scripts/generate_dataset.py") ||
      args.includes("scripts/sanitize_dataset.py") ||
      args.includes("scripts/export.py") ||
      args.includes("scripts/evaluate.py") ||
      args.includes("scripts/smoke_test.py");
    if (!isRelevant) continue;

    if (args.includes("server.ts") || args.includes("vite") || args.includes("npm run dev")) continue;

    discoveredPids.add(pid);

    let commandId = "pipeline";
    let type = "Pipeline";
    if (args.includes(" generate ") || args.includes("generate_dataset.py")) {
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
    } else if (args.includes(" evaluate ") || args.includes("smoke") || args.includes("evaluate.py") || args.includes("smoke_test.py")) {
      commandId = "evaluate";
      type = "Evaluation";
    }

    const npcMatch = args.match(/subjects\/([a-zA-Z0-9_\-]+)\.json/);
    const npcKey = npcMatch ? npcMatch[1] : undefined;
    const comboKey = `${commandId ?? ""}|${npcKey ?? ""}`;

    // --- Dedup: skip if we already track a running ext_proc for same (commandId, npcKey) ---
    if (trackedCombos.has(comboKey)) {
      continue;
    }
    trackedCombos.add(comboKey);

    const existingCombo = registry.jobs.find(
      (job) => job.id.startsWith("ext_proc_") && job.commandId === commandId && job.npcKey === npcKey && job.status === "running"
    );
    if (existingCombo) {
      continue;
    }

    const id = `ext_proc_${pid}`;
    const existing = registry.jobs.find((job) => job.id === id);
    if (existing) {
      if (existing.status !== "running") {
        existing.status = "running";
        existing.finishedAt = undefined;
        existing.exitCode = undefined;
        existing.terminalReason = "external_detected";
        appendStageLog(existing, `[EXTERNAL][PID ${pid}] Process still running`);
        changed = true;
      }
      continue;
    }

    const job: Job = {
      id,
      name: `External Process (${pid})${npcKey ? ` ${npcKey}` : ""}`,
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

    updateStagesFromTruth(job);
    registry.jobs.unshift(job);
    globalLog(registry, `[SYNC] discovered running external process pid=${pid}`);
    changed = true;
  }

  for (const job of registry.jobs) {
    if (!job.id.startsWith("ext_proc_")) continue;
    if (job.status !== "running") continue;

    const pid = Number(job.id.replace("ext_proc_", ""));
    if (!Number.isFinite(pid) || discoveredPids.has(pid)) continue;

    job.status = "stopped";
    job.finishedAt = now;
    job.exitCode = -15;
    job.terminalReason = "external_process_not_found";
    appendStageLog(job, `[EXTERNAL][PID ${pid}] Process no longer detected`);
    updateStagesFromTruth(job);
    changed = true;
  }

  if (changed) flushPersist(registry);
  return { changed, discovered: discoveredPids.size };
};

const validateRequiredFields = (payload: StartCommandPayload, requiredFields: string[]) => {
  for (const requiredField of requiredFields) {
    const [root, key] = requiredField.split(".");
    if (root === "options" && key) {
      const value = payload.options?.[key];
      if (value === undefined || value === null || String(value).trim() === "") {
        throw new Error(`${requiredField} is required.`);
      }
      continue;
    }

    const directValue = (payload as unknown as Record<string, unknown>)[requiredField];
    if (directValue === undefined || directValue === null || String(directValue).trim() === "") {
      throw new Error(`${requiredField} is required.`);
    }
  }
};

async function startServer() {
  const app = express();
  const PORT = Number(process.env.PORT || "3100");
  const registry = loadRegistry();
  reconcileOrphanedJobs(registry);
  syncExternalArtifactsToRegistry(registry);
  discoverActiveExternalProcesses(registry);

  app.use(express.json());

  // ── Security middleware: block path traversal ──
  app.use((req, res, next) => {
    // Use originalUrl (preserved by Express) to detect traversal in raw request.
    // req.path is parsed/normalized by Express which may resolve '..' sequences.
    const url = req.originalUrl ?? req.url;
    if (url.includes('..') || url.toLowerCase().includes('%2e')) {
      res.status(400).json({ error: 'Invalid path' });
      return;
    }
    next();
  });

  const listDatasets = () => {
    const datasetsRoot = path.join(repoRoot, "datasets");
    if (!fs.existsSync(datasetsRoot)) return [];
    return fs.readdirSync(datasetsRoot).map((npcKey) => {
      const npcPath = path.join(datasetsRoot, npcKey);
      if (!fs.statSync(npcPath).isDirectory()) return null;
      const versions = fs.readdirSync(npcPath)
        .filter((technique) => fs.statSync(path.join(npcPath, technique)).isDirectory())
        .map((technique) => {
          const trainPath = path.join(npcPath, technique, "train.jsonl");
          const entries = fs.existsSync(trainPath) ? fs.readFileSync(trainPath, "utf8").split("\n").filter(Boolean).length : 0;
          const stat = fs.existsSync(trainPath) ? fs.statSync(trainPath) : fs.statSync(path.join(npcPath, technique));
          return {
            tag: technique,
            size: `${Math.max(1, Math.round(stat.size / 1024))}KB`,
            entries,
            createdAt: stat.mtime.toISOString(),
          };
        });

      return { id: npcKey, name: npcKey, versions };
    }).filter(Boolean);
  };

  const listSubjects = () => {
    const subjectsRoot = path.join(repoRoot, "subjects");
    if (!fs.existsSync(subjectsRoot)) return [];
    return fs.readdirSync(subjectsRoot)
      .filter((f) => f.endsWith(".json"))
      .map((file) => ({ id: file.replace(/\.json$/, ""), path: `subjects/${file}` }));
  };

  const listRuns = () => {
    const outputsRoot = path.join(repoRoot, "outputs");
    if (!fs.existsSync(outputsRoot)) return [];
    return fs.readdirSync(outputsRoot)
      .filter((d) => fs.statSync(path.join(outputsRoot, d)).isDirectory())
      .map((d) => {
        const stat = fs.statSync(path.join(outputsRoot, d));
        return { id: d, npcKey: d, updatedAt: stat.mtime.toISOString() };
      });
  };

  const listExports = () => {
    const exportsRoot = path.join(repoRoot, "exports");
    if (!fs.existsSync(exportsRoot)) return [];
    const entries: Array<{ npcKey: string; file: string; updatedAt: string }> = [];
    for (const npcKey of fs.readdirSync(exportsRoot)) {
      const npcDir = path.join(exportsRoot, npcKey);
      if (!fs.statSync(npcDir).isDirectory()) continue;
      for (const file of fs.readdirSync(npcDir).filter((f) => f.endsWith(".gguf"))) {
        const stat = fs.statSync(path.join(npcDir, file));
        entries.push({ npcKey, file: `exports/${npcKey}/${file}`, updatedAt: stat.mtime.toISOString() });
      }
    }
    return entries;
  };

  // API Routes
  app.get("/api/jobs", (_req, res) => {
    syncExternalArtifactsToRegistry(registry);
    discoverActiveExternalProcesses(registry);
    res.json(registry.jobs);
  });
  app.get("/api/logs", (_req, res) => res.json(registry.logs));

  app.get("/api/analytics", (req, res) => {
    const jobId = typeof req.query.jobId === "string" ? req.query.jobId : "";
    const job = registry.jobs.find((item) => item.id === jobId) ?? registry.jobs[0];
    if (!job) return res.json([]);

    const points: Array<{ step: number; loss: number; acc: number; lr: number }> = [];
    let step = 0;
    for (const line of job.logs) {
      const loss = parseLoss(line);
      if (loss === null) continue;
      step += 1;
      points.push({ step, loss, acc: Math.max(0, Math.min(1, 1 - loss / 3)), lr: Number((2e-4 / Math.max(1, step)).toPrecision(4)) });
    }
    res.json(points);
  });

  app.get("/api/available-commands", (_req, res) => res.json(commandDefinitions.map(({ build, ...rest }) => rest)));

  const listPresets = () => {
    const presetsDir = path.join(repoRoot, "configs", "presets");
    const presets: Array<{ name: string; description: string }> = [];

    try {
      for (const file of fs.readdirSync(presetsDir)) {
        if (!(file.endsWith(".yaml") || file.endsWith(".yml"))) continue;
        const name = file.replace(/\.ya?ml$/, "");
        let description = "";
        try {
          const content = fs.readFileSync(path.join(presetsDir, file), "utf8");
          const firstLine = content.split("\n").find((l) => l.trim().startsWith("#"));
          if (firstLine) description = firstLine.replace(/^\s*#\s*/, "").trim();
        } catch {
          // ignore malformed preset files
        }
        presets.push({ name, description });
      }
    } catch {
      // presets dir may not exist
    }

    return presets.sort((a, b) => a.name.localeCompare(b.name));
  };

  app.get("/api/presets", (_req, res) => {
    res.json(listPresets());
  });

  app.get("/api/config/presets", (_req, res) => {
    res.json(listPresets());
  });


  let assistantContext = "";
  try {
    const agentsMd = fs.readFileSync(path.join(repoRoot, "AGENTS.md"), "utf8");
    const cliRef = fs.readFileSync(path.join(repoRoot, "docs/reference/CLI_REFERENCE.md"), "utf8");
    assistantContext = `
PROJECT CONTEXT (AGENTS.md):
${agentsMd}

CLI REFERENCE:
${cliRef}
    `;
  } catch (err) {
    console.warn("Failed to load assistant context files:", err);
  }

  app.post("/api/assistant", async (req, res) => {
    const message = typeof req.body?.message === "string" ? req.body.message.trim() : "";
    const history = Array.isArray(req.body?.history) ? req.body.history : [];
    if (!message) return res.status(400).json({ error: "message is required" });

    try {
      const messages: Array<{ role: string; content: string }> = [
        {
          role: "system",
          content: `You are a high-level specialist in Unity NPC LLM integration and the Unsloth_Core pipeline.
Keep responses concise and actionable. Use the following context for your knowledge:

${assistantContext}

If the user asks to run a command, you can suggest the exact ./ucore command.
You also have access to an E2B sandbox for filesystem analysis if E2B_API_KEY is set.`,
        },
        ...history.slice(-10),
        { role: "user", content: message },
      ];

      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 60_000);
      let response: Response;

      try {
        response = await fetch("http://127.0.0.1:11434/api/chat", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            model: "gemma4:e2b",
            messages,
            stream: false,
            options: { temperature: 0.7, num_predict: 2048 },
          }),
          signal: controller.signal,
        });
      } finally {
        clearTimeout(timeout);
      }

      if (!response.ok) {
        const text = await response.text();
        return res.status(502).json({ error: `Ollama request failed: ${text}` });
      }

      const body = await response.json() as {
        message?: { content?: string };
        done?: boolean;
      };
      const content = body.message?.content?.trim();
      return res.json({ content: content || "No assistant response generated." });
    } catch (error) {
      if (error instanceof Error && error.name === "AbortError") {
        return res.status(504).json({ error: "Assistant request timed out after 60 seconds.", timeout: true });
      }
      const messageText = error instanceof Error ? error.message : "Assistant request failed.";
      if (messageText.includes("ECONNREFUSED") || messageText.includes("fetch failed")) {
        return res.json({
          content: "**Ollama is not running.** Start it with `ollama serve` or `ollama run gemma4:e2b`, then try again.",
        });
      }
      return res.status(500).json({ error: messageText });
    }
  });

  app.get("/api/dataset/:npcKey/:technique", (req, res) => {
    const { npcKey, technique } = req.params;
    const n = Math.min(Math.max(parseInt(String(req.query.n || "10"), 10) || 10, 1), 100);

    // Security: reject path traversal
    if (npcKey.includes("..") || technique.includes("..")) {
      return res.status(400).json({ error: "Invalid path" });
    }

    const trainPath = path.join(repoRoot, "datasets", npcKey, technique, "train.jsonl");
    if (!fs.existsSync(trainPath)) {
      return res.status(404).json({ error: `Dataset ${npcKey}/${technique} not found. Run generation first.` });
    }

    try {
      const content = fs.readFileSync(trainPath, "utf8");
      const lines = content.split("\n").filter(Boolean);
      const total = lines.length;
      const samples = lines.slice(0, n).map((line, i) => {
        try {
          return JSON.parse(line);
        } catch {
          return { _parseError: true, _line: i, _raw: line.slice(0, 200) };
        }
      });

      return res.json({
        npcKey,
        technique,
        total,
        samples,
        showing: Math.min(n, total),
      });
    } catch (err) {
      return res.status(500).json({ error: err instanceof Error ? err.message : "Failed to read dataset" });
    }
  });

  app.get("/api/datasets", (_req, res) => res.json(listDatasets()));
  app.get("/api/subjects", (_req, res) => res.json(listSubjects()));
  app.get("/api/runs", (_req, res) => res.json(listRuns()));

  app.get("/api/eval-reports", (_req, res) => {
    const evalRoot = path.join(repoRoot, "eval");
    const reports: Array<{ npcKey: string; files: Array<{ name: string; path: string }> }> = [];
    const comparisons: Array<{ name: string; path: string }> = [];

    const reportsDir = path.join(evalRoot, "reports");
    if (fs.existsSync(reportsDir)) {
      for (const npcDir of fs.readdirSync(reportsDir)) {
        const npcPath = path.join(reportsDir, npcDir);
        if (!fs.statSync(npcPath).isDirectory()) continue;
        const files = fs.readdirSync(npcPath).map((f) => ({
          name: f,
          path: `eval/reports/${npcDir}/${f}`,
        }));
        reports.push({ npcKey: npcDir, files });
      }
    }

    const compDir = path.join(evalRoot, "comparisons");
    if (fs.existsSync(compDir)) {
      for (const f of fs.readdirSync(compDir)) {
        const fPath = path.join(compDir, f);
        if (!fs.statSync(fPath).isFile()) continue;
        comparisons.push({ name: f, path: `eval/comparisons/${f}` });
      }
    }

    return res.json({ reports, comparisons });
  });

  app.get("/api/run/:npcKey/:runId", (req, res) => {
    const { npcKey, runId } = req.params;

    if (npcKey.includes("..") || runId.includes("..")) {
      return res.status(400).json({ error: "Invalid path" });
    }

    const runPath = path.join(repoRoot, "outputs", npcKey, "runs", runId);
    if (!fs.existsSync(runPath)) {
      return res.status(404).json({ error: `Run ${npcKey}/${runId} not found` });
    }

    // Read config.yaml if exists
    let config: Record<string, unknown> = {};
    const configPath = path.join(runPath, "config.yaml");
    if (fs.existsSync(configPath)) {
      try {
        // Simple YAML to JSON parser for basic key-value pairs
        const raw = fs.readFileSync(configPath, "utf8");
        config = Object.fromEntries(
          raw
            .split("\n")
            .filter((l) => l.includes(":"))
            .map((l) => {
              const [k, ...v] = l.split(":");
              return [k.trim(), v.join(":").trim()];
            })
        );
      } catch { /* ignore parse errors */ }
    }

    // Read metrics.json if exists
    let metrics: Record<string, unknown> = {};
    const metricsPath = path.join(runPath, "metrics.json");
    if (fs.existsSync(metricsPath)) {
      try {
        metrics = JSON.parse(fs.readFileSync(metricsPath, "utf8"));
      } catch { /* ignore parse errors */ }
    }

    return res.json({
      npcKey,
      runId,
      path: runPath,
      config,
      metrics,
    });
  });

  app.get("/api/exports", (_req, res) => res.json(listExports()));
  app.get("/api/execution-mode", (_req, res) => res.json({ mode: registry.executionMode }));
  app.post("/api/execution-mode", (req, res) => {
    const mode = req.body?.mode;
    if (mode !== "local" && mode !== "remote") return res.status(400).json({ error: "Invalid mode." });
    registry.executionMode = mode;
    persistRegistry(registry);
    return res.json({ mode });
  });
  app.get("/api/system/status", (_req, res) => {
    res.json({
      executionMode: registry.executionMode,
      runningJobs: registry.jobs.filter((job) => job.status === "running").length,
      totalJobs: registry.jobs.length,
      repoRoot,
      timestamp: isoNow(),
    });
  });

  app.get("/api/health", (_req, res) => {
    const coreChecks = {
      ucoreExists: fs.existsSync(path.join(repoRoot, "ucore")),
      subjectsDir: fs.existsSync(path.join(repoRoot, "subjects")),
      datasetsDir: fs.existsSync(path.join(repoRoot, "datasets")),
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
      timestamp: isoNow(),
    });
  });

  app.get("/api/telemetry", (_req, res) => {
    res.json(buildTelemetryPayload(registry.nodeId));
  });

  app.get("/api/docs", (_req, res) => {
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
      } catch { /* directory may not exist */ }
    };
    if (fs.existsSync(docsRoot)) walk(docsRoot);
    // Also include AGENTS.md in root
    const agentsMd = path.join(repoRoot, "AGENTS.md");
    if (fs.existsSync(agentsMd)) results.unshift("AGENTS.md");
    res.json(results);
  });

  app.get("/api/tensorboard", (req, res) => {
    const runId = typeof req.query.runId === "string" ? req.query.runId.trim() : "";
    if (!runId) return res.json({ runId: "", scalars: {}, error: "runId query parameter is required" });

    // Look for run dirs in outputs/*/runs/ matching the runId
    const outputsRoot = path.join(repoRoot, "outputs");
    // Find the run directory by searching all npc outputs
    let runDir = "";
    if (fs.existsSync(outputsRoot)) {
      for (const npcKey of fs.readdirSync(outputsRoot)) {
        const runsDir = path.join(outputsRoot, npcKey, "runs");
        if (!fs.existsSync(runsDir)) continue;
        const candidate = path.join(runsDir, runId);
        if (fs.existsSync(candidate) && fs.statSync(candidate).isDirectory()) {
          runDir = candidate;
          break;
        }
      }
    }

    if (!runDir) {
      return res.json({ runId, scalars: {}, error: `Run directory not found for ${runId}` });
    }

    try {
      const result = execSync(
        `python scripts/tb_reader.py --run-dir "${runDir}"`,
        { cwd: repoRoot, encoding: "utf8", timeout: 10000 }
      );
      const data = JSON.parse(result.trim());
      return res.json(data);
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Failed to read TensorBoard data";
      return res.json({ runId, scalars: {}, error: msg });
    }
  });

  // ── Supabase Integration ──────────────────────────────────────────────────

  app.get("/api/supabase/status", async (_req, res) => {
    const supabaseUrl = process.env.SUPABASE_URL || "";
    const supabaseKey = process.env.SUPABASE_KEY || "";
    if (!supabaseUrl || !supabaseKey) {
      return res.json({ connected: false, url: "", error: "SUPABASE_URL and SUPABASE_KEY not configured" });
    }
    try {
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 5000);
      let response;
      try {
        response = await fetch(`${supabaseUrl}/rest/v1/npc_profiles?select=npc_id&limit=1`, {
          headers: { "apikey": supabaseKey, "Authorization": `Bearer ${supabaseKey}` },
          signal: controller.signal,
        });
      } finally {
        clearTimeout(timeout);
      }
      res.json({ connected: response.ok, url: supabaseUrl, error: response.ok ? undefined : `Health check failed: ${response.status}` });
    } catch (err: any) {
      res.json({ connected: false, url: supabaseUrl, error: err.message });
    }
  });

  app.get("/api/supabase/leaderboard", async (_req, res) => {
    const supabaseUrl = process.env.SUPABASE_URL || "";
    const supabaseKey = process.env.SUPABASE_KEY || "";
    if (!supabaseUrl || !supabaseKey) {
      return res.json({ entries: [], status: { connected: false, url: "", error: "Supabase not configured" } });
    }
    try {
      // Fetch top test results ordered by score
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 5000);
      let response;
      try {
        response = await fetch(
          `${supabaseUrl}/rest/v1/test_results?select=*&order=score.desc&limit=20`,
          { headers: { "apikey": supabaseKey, "Authorization": `Bearer ${supabaseKey}` }, signal: controller.signal }
        );
      } finally {
        clearTimeout(timeout);
      }
      if (!response.ok) throw new Error(`Supabase query failed: ${response.status}`);
      const data = await response.json();
      const entries = data.map((row: any, i: number) => ({
        rank: i + 1,
        npc_id: row.npc_id,
        npc_name: row.npc_id,
        test_name: row.test_name,
        score: row.score,
        metrics: row.metrics || {},
      }));
      res.json({ entries, status: { connected: true, url: supabaseUrl } });
    } catch (err: any) {
      res.json({ entries: [], status: { connected: false, url: supabaseUrl, error: err.message } });
    }
  });

  app.get("/api/supabase/npc-profiles", async (_req, res) => {
    const supabaseUrl = process.env.SUPABASE_URL || "";
    const supabaseKey = process.env.SUPABASE_KEY || "";
    if (!supabaseUrl || !supabaseKey) {
      return res.json({ profiles: [], status: { connected: false, url: "", error: "Supabase not configured" } });
    }
    try {
      const response = await fetch(
        `${supabaseUrl}/rest/v1/npc_profiles?select=*&order=created_at.desc`,
        { headers: { "apikey": supabaseKey, "Authorization": `Bearer ${supabaseKey}` } }
      );
      if (!response.ok) throw new Error(`Supabase query failed: ${response.status}`);
      const data = await response.json();
      res.json({ profiles: data, status: { connected: true, url: supabaseUrl } });
    } catch (err: any) {
      res.json({ profiles: [], status: { connected: false, url: supabaseUrl, error: err.message } });
    }
  });

  // ── End Supabase Integration ──────────────────────────────────────────────

  // ── Unity Deployment ──────────────────────────────────────────────────────

  app.get("/api/unity/status", (_req, res) => {
    const exportsRoot = path.join(repoRoot, "exports");
    const npcs: Array<{ npcKey: string; ggufFiles: Array<{ name: string; sizeMB: number; quant: string }>; manifest: Record<string, unknown> }> = [];

    if (fs.existsSync(exportsRoot)) {
      for (const npcDir of fs.readdirSync(exportsRoot)) {
        const npcPath = path.join(exportsRoot, npcDir);
        if (!fs.statSync(npcPath).isDirectory()) continue;
        const ggufFiles = fs.readdirSync(npcPath)
          .filter((f) => f.endsWith(".gguf"))
          .map((f) => {
            const stat = fs.statSync(path.join(npcPath, f));
            const quant = f.includes("q4_k_m") ? "q4_k_m" : f.includes("f16") ? "f16" : f.includes("q8_0") ? "q8_0" : "unknown";
            return { name: f, sizeMB: Math.round(stat.size / (1024 * 1024) * 10) / 10, quant };
          });
        let manifest: Record<string, unknown> = {};
        const manifestPath = path.join(npcPath, "manifest.json");
        if (fs.existsSync(manifestPath)) {
          try { manifest = JSON.parse(fs.readFileSync(manifestPath, "utf8")); } catch {}
        }
        npcs.push({ npcKey: npcDir, ggufFiles, manifest });
      }
    }

    // Detect Unity project (same logic as deploy_to_unity.py: sibling dir with Assets/ + ProjectSettings/)
    let unityProjectPath = "";
    const parent = path.resolve(repoRoot, "..");
    if (fs.existsSync(parent)) {
      const candidates = fs.readdirSync(parent).filter((entry) => {
        const entryPath = path.join(parent, entry);
        if (entry === path.basename(repoRoot)) return false;
        try {
          return fs.statSync(path.join(entryPath, "Assets")).isDirectory() &&
                 fs.statSync(path.join(entryPath, "ProjectSettings")).isDirectory();
        } catch { return false; }
      });
      if (candidates.length === 1) {
        unityProjectPath = path.resolve(parent, candidates[0]);
      } else if (candidates.length > 1) {
        // Store the first one
        unityProjectPath = path.resolve(parent, candidates[0]);
      }
    }

    const streamingModelsPath = unityProjectPath ? path.join(unityProjectPath, "Assets", "StreamingAssets", "Models") : "";
    const deployedFiles: string[] = [];
    if (streamingModelsPath && fs.existsSync(streamingModelsPath)) {
      const files = fs.readdirSync(streamingModelsPath).filter((f) => f.endsWith(".gguf"));
      for (const f of files) {
        const fPath = path.join(streamingModelsPath, f);
        const stat = fs.statSync(fPath);
        deployedFiles.push(`${f} (${Math.round(stat.size / (1024 * 1024))}MB)`);
      }
    }

    res.json({
      exported: npcs,
      unityProject: unityProjectPath || null,
      deployedFiles,
      deployScript: fs.existsSync(path.join(repoRoot, "scripts", "deploy_to_unity.py")),
    });
  });

  app.post("/api/unity/deploy", (req, res) => {
    try {
      const dryRun = req.body?.dryRun === true;
      const cmd = ["python", "scripts/deploy_to_unity.py"];
      if (dryRun) cmd.push("--dry-run");
      if (req.body?.npcKey) {
        cmd.push("--npc-key", sanitizeToken(String(req.body.npcKey), "npcKey"));
      }
      const result = require("child_process").execSync(cmd.join(" "), {
        cwd: repoRoot,
        encoding: "utf8",
        timeout: 30000,
      });
      res.json({ success: true, output: result.trim(), dryRun });
    } catch (err: any) {
      const output = err.stdout?.toString() || err.message || "Deploy failed";
      res.status(500).json({ success: false, output, error: err.message });
    }
  });

  app.get("/api/remote-config", (_req, res) => {
    res.json({
      configured: Boolean(process.env.REMOTE_API_URL && process.env.REMOTE_API_KEY),
      remoteUrl: process.env.REMOTE_API_URL || "",
      hasKey: Boolean(process.env.REMOTE_API_KEY),
      mode: registry.executionMode,
    });
  });

  // ── End Unity Deployment ──────────────────────────────────────────────────

  // ── Workflow Chaining ─────────────────────────────────────────────────────

  app.get("/api/workflows", (_req, res) => {
    res.json(registry.workflows);
  });

  app.post("/api/workflow/start", (req, res) => {
    try {
      const spec = String(req.body?.spec || "").trim();
      const preset = String(req.body?.preset || "").trim();
      const technique = String(req.body?.technique || "notebooklm").trim();
      if (!spec) return res.status(400).json({ error: "spec is required" });

      const npcKey = spec.replace(/^subjects\//, "").replace(/\.json$/, "");
      const workflowId = `wf_${Date.now()}`;

      const steps: WorkflowStep[] = [
        { commandId: "dataset-generate", status: "pending", payload: { commandId: "dataset-generate", type: "Dataset", spec, options: { technique } } },
        { commandId: "dataset-sanitize", status: "pending", payload: { commandId: "dataset-sanitize", type: "Dataset", spec, options: { datasetPath: `datasets/${npcKey}/${technique}/train.jsonl` } } },
        { commandId: "train", status: "pending", payload: { commandId: "train", type: "Training", spec, preset, npcKey, options: { ...req.body?.options || {} } } },
        { commandId: "export", status: "pending", payload: { commandId: "export", type: "Export", npcKey, options: { modelId: String(req.body?.options?.baseModel || "") } } },
      ];

      const workflow: Workflow = {
        id: workflowId,
        name: `Pipeline: ${npcKey} (${preset || "default"})`,
        spec,
        steps,
        currentStep: 0,
        overallStatus: "running",
        createdAt: isoNow(),
      };

      registry.workflows.unshift(workflow);
      flushPersist(registry);

      // Start the first step
      const firstStep = steps[0];
      const firstDef = commandMap.get(firstStep.commandId);
      if (!firstDef) return res.status(500).json({ error: `Unknown command: ${firstStep.commandId}` });

      const command = firstDef.build(firstStep.payload as StartCommandPayload);
      const chainNext = steps.length > 1 ? {
        commandId: steps[1].commandId,
        payload: steps[1].payload,
      } : undefined;

      const job: Job = {
        id: makeId(),
        name: `${firstDef.label} (${npcKey})`,
        type: firstDef.type,
        commandId: firstDef.id,
        npcKey,
        workflowId,
        chainNext,
        status: "running",
        progress: 5,
        loss: null,
        createdAt: isoNow(),
        startedAt: isoNow(),
        command,
        stages: defaultStages(),
        logs: [],
      };
      updateStagesFromTruth(job);

      firstStep.status = "running";
      firstStep.jobId = job.id;
      registry.jobs.unshift(job);
      globalLog(registry, `[WORKFLOW] starting ${workflowId} step 1/${steps.length}: ${command.join(" ")}`);
      persistRegistry(registry);
      broadcast("job_update", { id: job.id, status: job.status, loss: job.loss, progress: job.progress });

      const child = spawn(command[0], command.slice(1), { cwd: repoRoot, shell: false, detached: true });
      runningProcesses.set(job.id, child);
      terminalJobState.set(job.id, { stopRequested: false, terminal: false });

      const consume = (chunk: Buffer, source: "stdout" | "stderr") => {
        const lines = chunk.toString().split("\n").map((l) => l.trim()).filter(Boolean);
        for (const line of lines) {
          const prefixed = `[${source.toUpperCase()}][${job.id}] ${line}`;
          job.logs.push(prefixed);
          job.logs = job.logs.slice(-MAX_LOG_LINES);
          appendStageLog(job, prefixed);
          globalLog(registry, prefixed);
          const parsedLoss = parseLoss(line);
          if (parsedLoss !== null) {
            job.loss = parsedLoss;
            broadcast("job_update", { id: job.id, status: job.status, loss: job.loss, progress: job.progress });
          }
          updateStagesFromTruth(job);
        }
        persistRegistry(registry);
      };

      child.stdout.on("data", (chunk) => consume(chunk, "stdout"));
      child.stderr.on("data", (chunk) => consume(chunk, "stderr"));
      child.on("close", (code) => {
        const terminalState = terminalJobState.get(job.id);
        const escalationTimer = stopEscalationTimers.get(job.id);
        if (escalationTimer) {
          clearTimeout(escalationTimer);
          stopEscalationTimers.delete(job.id);
        }
        runningProcesses.delete(job.id);
        terminalJobState.delete(job.id);
        if (terminalState?.terminal) return;

        job.exitCode = code ?? -1;
        job.finishedAt = isoNow();
        if (terminalState?.stopRequested || job.stopRequested) {
          job.status = "stopped";
          job.terminalReason = "user_requested_stop";
        } else {
          job.status = code === 0 ? "completed" : "failed";
        }

        firstStep.status = code === 0 ? "completed" : "failed";
        workflow.currentStep = 1;

        if (code !== 0) {
          workflow.overallStatus = "failed";
          workflow.finishedAt = isoNow();
        }

        updateStagesFromTruth(job);
        globalLog(registry, `[SYSTEM] ${job.id} ${job.status} (exit ${code})`);
        flushPersist(registry);
        broadcast("job_update", { id: job.id, status: job.status, loss: job.loss, progress: job.progress });

        // Chain to next step
        if (code === 0 && chainNext) {
          const nextDef = commandMap.get(chainNext.commandId);
          if (nextDef) {
            try {
              globalLog(registry, `[WORKFLOW] chaining to step 2: ${chainNext.commandId}`);
              const nextCommand = nextDef.build(chainNext.payload as StartCommandPayload);
              const nextChain = steps.length > 2 ? {
                commandId: steps[2].commandId,
                payload: steps[2].payload,
              } : undefined;

              const nextJob: Job = {
                id: makeId(),
                name: `${nextDef.label} (${npcKey})`,
                type: nextDef.type,
                commandId: nextDef.id,
                npcKey,
                workflowId,
                chainNext: nextChain,
                status: "running",
                progress: 5,
                loss: null,
                createdAt: isoNow(),
                startedAt: isoNow(),
                command: nextCommand,
                stages: defaultStages(),
                logs: [],
              };
              updateStagesFromTruth(nextJob);

              const stepIndex = 1;
              steps[stepIndex].status = "running";
              steps[stepIndex].jobId = nextJob.id;
              registry.jobs.unshift(nextJob);
              globalLog(registry, `[WORKFLOW] starting step ${stepIndex + 1}/${steps.length}: ${nextCommand.join(" ")}`);
              persistRegistry(registry);
              broadcast("job_update", { id: nextJob.id, status: nextJob.status, loss: nextJob.loss, progress: nextJob.progress });

              const nextChild = spawn(nextCommand[0], nextCommand.slice(1), { cwd: repoRoot, shell: false, detached: true });
              runningProcesses.set(nextJob.id, nextChild);
              terminalJobState.set(nextJob.id, { stopRequested: false, terminal: false });

              const nextConsume = (chunk: Buffer, source: "stdout" | "stderr") => {
                const lines = chunk.toString().split("\n").map((l) => l.trim()).filter(Boolean);
                for (const line of lines) {
                  const prefixed = `[${source.toUpperCase()}][${nextJob.id}] ${line}`;
                  nextJob.logs.push(prefixed);
                  nextJob.logs = nextJob.logs.slice(-MAX_LOG_LINES);
                  appendStageLog(nextJob, prefixed);
                  globalLog(registry, prefixed);
                  const parsedLoss = parseLoss(line);
                  if (parsedLoss !== null) {
                    nextJob.loss = parsedLoss;
                    broadcast("job_update", { id: nextJob.id, status: nextJob.status, loss: nextJob.loss, progress: nextJob.progress });
                  }
                  updateStagesFromTruth(nextJob);
                }
                persistRegistry(registry);
              };

              nextChild.stdout.on("data", (chunk) => nextConsume(chunk, "stdout"));
              nextChild.stderr.on("data", (chunk) => nextConsume(chunk, "stderr"));
              nextChild.on("close", (nextCode) => {
                const nextTerminalState = terminalJobState.get(nextJob.id);
                const nextEscalationTimer = stopEscalationTimers.get(nextJob.id);
                if (nextEscalationTimer) {
                  clearTimeout(nextEscalationTimer);
                  stopEscalationTimers.delete(nextJob.id);
                }
                runningProcesses.delete(nextJob.id);
                terminalJobState.delete(nextJob.id);
                if (nextTerminalState?.terminal) return;

                nextJob.exitCode = nextCode ?? -1;
                nextJob.finishedAt = isoNow();
                if (nextTerminalState?.stopRequested || nextJob.stopRequested) {
                  nextJob.status = "stopped";
                  nextJob.terminalReason = "user_requested_stop";
                } else {
                  nextJob.status = nextCode === 0 ? "completed" : "failed";
                }

                steps[stepIndex].status = nextCode === 0 ? "completed" : "failed";
                workflow.currentStep = stepIndex + 1;

                if (nextCode !== 0) {
                  workflow.overallStatus = "failed";
                  workflow.finishedAt = isoNow();
                } else if (stepIndex === steps.length - 1) {
                  workflow.overallStatus = "completed";
                  workflow.finishedAt = isoNow();
                }

                updateStagesFromTruth(nextJob);
                globalLog(registry, `[SYSTEM] ${nextJob.id} ${nextJob.status} (exit ${nextCode})`);
                flushPersist(registry);
                broadcast("job_update", { id: nextJob.id, status: nextJob.status, loss: nextJob.loss, progress: nextJob.progress });
              });
            } catch (chainErr) {
              globalLog(registry, `[WORKFLOW] chaining failed: ${chainErr instanceof Error ? chainErr.message : String(chainErr)}`);
              workflow.overallStatus = "failed";
              workflow.finishedAt = isoNow();
              flushPersist(registry);
            }
          }
        }
      });

      res.json({ workflow, job });
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to start workflow";
      res.status(400).json({ error: message });
    }
  });

  // ── End Workflow Chaining ─────────────────────────────────────────────────

  app.get("/api/suggestions", (_req, res) => {
    const suggestions = [
      "Check Rank size for QuestGiver LoRA if loss plateau persists.",
      "Ensure dataset entries have consistent dialogue format.",
      "Verify Unity NPC protocol v4 compatibility in exports.",
      "Monitor GPU memory usage during training phases.",
      "Adjust temperature to 0.4 for better dialogue coherence.",
    ];
    res.json({ suggestions });
  });

  app.get("/api/command-schemas", (_req, res) => {
    type FieldSchema = {
      type: "string" | "number" | "boolean";
      required: boolean;
      default?: string | number | boolean;
      description?: string;
      enum?: string[];
    };

    const presetOptions = listPresets().map((p) => p.name);

    const baseDefaultsByCommand: Record<string, Record<string, FieldSchema>> = {
      "dataset-generate": {
        spec: { type: "string", required: true, default: "subjects/chemistry_instructor.json", description: "Subject spec path" },
        "options.technique": { type: "string", required: false, default: "ollama", enum: ["notebooklm", "ollama", "template", "openai", "anthropic"] },
      },
      "dataset-sanitize": {
        "options.datasetPath": { type: "string", required: true, default: "datasets/chemistry_instructor/ollama/train.jsonl", description: "Train dataset path" },
      },
      train: {
        spec: { type: "string", required: true, default: "subjects/chemistry_instructor.json" },
        preset: { type: "string", required: false, default: "llama-1b-fast", ...(presetOptions.length ? { enum: presetOptions } : {}) },
        "options.learningRate": { type: "string", required: false, default: "2e-4" },
        "options.batchSize": { type: "number", required: false, default: 1 },
        "options.epochs": { type: "number", required: false, default: 3 },
        "options.rank": { type: "number", required: false, default: 16 },
        "options.alpha": { type: "number", required: false, default: 32 },
      },
      pipeline: {
        spec: { type: "string", required: true, default: "subjects/chemistry_instructor.json" },
        preset: { type: "string", required: false, default: "llama-1b-fast", ...(presetOptions.length ? { enum: presetOptions } : {}) },
        "options.technique": { type: "string", required: false, default: "ollama", enum: ["notebooklm", "ollama", "template", "openai", "anthropic"] },
        "options.track": { type: "boolean", required: false, default: false },
      },
      export: {
        npcKey: { type: "string", required: true, default: "chemistry_instructor" },
        "options.modelId": { type: "string", required: true, default: "unsloth/Llama-3.2-1B-Instruct-bnb-4bit" },
      },
      "export-adapter": {
        npcKey: { type: "string", required: true, default: "chemistry_instructor" },
      },
      evaluate: {
        spec: { type: "string", required: true, default: "subjects/chemistry_instructor.json" },
        "options.baseline": { type: "string", required: true, default: "exports/default/default-llama3.2-3b-f16.gguf" },
        "options.candidate": { type: "string", required: true, default: "exports/chemistry_instructor/chemistry_instructor-llama3.2-1b-f16.gguf" },
        "options.valData": { type: "string", required: false, default: "" },
      },
      smoke: {
        spec: { type: "string", required: true, default: "subjects/chemistry_instructor.json" },
        "options.modelPath": { type: "string", required: true, default: "exports/chemistry_instructor/chemistry_instructor-llama3.2-1b-f16.gguf" },
      },
      deploy: {
        "options.npcKey": { type: "string", required: true, default: "chemistry_instructor" },
        "options.modelId": { type: "string", required: true, default: "unsloth/Llama-3.2-1B-Instruct-bnb-4bit" },
      },
      "supabase-check": {
        npcKey: { type: "string", required: true, default: "chemistry_instructor" },
        "options.playerId": { type: "string", required: false, default: "" },
      },
    };

    const schemas: Record<string, { fields: Record<string, FieldSchema> }> = {};

    for (const [id, def] of commandMap.entries()) {
      const fields: Record<string, FieldSchema> = {};

      for (const requiredField of def.requiredFields) {
        fields[requiredField] = {
          type: "string",
          required: true,
          description: `Required by ${id}`,
        };
      }

      const defaults = baseDefaultsByCommand[id] || {};
      for (const [k, v] of Object.entries(defaults)) {
        fields[k] = { ...fields[k], ...v };
      }

      fields.commandId = {
        type: "string",
        required: true,
        default: id,
        description: "Backend command identifier",
      };

      schemas[id] = { fields };
    }

    res.json(schemas);
  });

  app.post("/api/commands/start", (req, res) => {
    try {
      const payload = req.body as StartCommandPayload;
      const commandDef = commandMap.get(payload.commandId || "");
      if (!commandDef) return res.status(400).json({ error: "Unknown commandId." });
      if (registry.executionMode === "remote") {
        return res.status(501).json({ error: "Remote runner not implemented yet.", mode: "remote" });
      }

      validateRequiredFields(payload, commandDef.requiredFields);

      const command = commandDef.build(payload);
      const job: Job = {
        id: makeId(),
        name: `${commandDef.label}${payload.npcKey ? ` (${payload.npcKey})` : ""}`,
        type: payload.type || commandDef.type,
        commandId: commandDef.id,
        npcKey: payload.npcKey,
        status: "running",
        progress: 5,
        loss: null,
        createdAt: isoNow(),
        startedAt: isoNow(),
        command,
        stages: defaultStages(),
        logs: [],
      };
      updateStagesFromTruth(job);

      registry.jobs.unshift(job);
      globalLog(registry, `[SYSTEM] starting ${job.id}: ${command.join(" ")}`);
      persistRegistry(registry);
      broadcast("job_update", { id: job.id, status: job.status, loss: job.loss, progress: job.progress });

      const child = spawn(command[0], command.slice(1), { cwd: repoRoot, shell: false, detached: true });
      runningProcesses.set(job.id, child);
      terminalJobState.set(job.id, { stopRequested: false, terminal: false });

      const consume = (chunk: Buffer, source: "stdout" | "stderr") => {
        const lines = chunk.toString().split("\n").map((line) => line.trim()).filter(Boolean);
        for (const line of lines) {
          const prefixed = `[${source.toUpperCase()}][${job.id}] ${line}`;
          job.logs.push(prefixed);
          job.logs = job.logs.slice(-MAX_LOG_LINES);
          appendStageLog(job, prefixed);
          globalLog(registry, prefixed);

          // Extract W&B run URL from wandb output
          const wandbMatch = line.match(/https:\/\/wandb\.ai\/[-a-zA-Z0-9./_?=&#%~]+\/runs\/([a-z0-9]+)/i);
          if (wandbMatch) {
            const wandbUrl = wandbMatch[0];
            if (!job.wandbUrl) {
              job.wandbUrl = wandbUrl;
              globalLog(registry, `[WANDB] captured run URL: ${wandbUrl}`);
              broadcast("job_update", { id: job.id, status: job.status, loss: job.loss, progress: job.progress, wandbUrl });
            }
          }

          const parsedLoss = parseLoss(line);
          if (parsedLoss !== null) {
            job.loss = parsedLoss;
            broadcast("job_update", { id: job.id, status: job.status, loss: job.loss, progress: job.progress });
          }
          updateStagesFromTruth(job);
        }
        persistRegistry(registry);
      };

      child.stdout.on("data", (chunk) => consume(chunk, "stdout"));
      child.stderr.on("data", (chunk) => consume(chunk, "stderr"));
      child.on("close", (code) => {
        const terminalState = terminalJobState.get(job.id);
        const escalationTimer = stopEscalationTimers.get(job.id);
        if (escalationTimer) {
          clearTimeout(escalationTimer);
          stopEscalationTimers.delete(job.id);
        }
        runningProcesses.delete(job.id);
        terminalJobState.delete(job.id);

        if (terminalState?.terminal) {
          return;
        }

        job.exitCode = code ?? -1;
        job.finishedAt = isoNow();
        if (terminalState?.stopRequested || job.stopRequested) {
          job.status = "stopped";
          job.terminalReason = "user_requested_stop";
        } else {
          job.status = code === 0 ? "completed" : "failed";
        }
        updateStagesFromTruth(job);
        globalLog(registry, `[SYSTEM] job ${job.id} ${job.status} (exit ${code})`);
        flushPersist(registry);
        broadcast("job_update", { id: job.id, status: job.status, loss: job.loss, progress: job.progress });
      });

      res.json(job);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to start command.";
      res.status(400).json({ error: message });
    }
  });

  app.post("/api/commands/stop", (req, res) => {
    const { id } = req.body as { id?: string };
    if (!id) return res.status(400).json({ error: "id is required" });
    const proc = runningProcesses.get(id);
    const job = registry.jobs.find((item) => item.id === id);
    if (!job) return res.status(404).json({ error: "Job not found" });
    if (!proc) return res.status(409).json({ error: "Job is not running" });

    // Negative PID kills the entire process group (detached: true ensures proc.pid == pgid)
    try { process.kill(-proc.pid, "SIGTERM"); } catch { proc.kill("SIGTERM"); }
    const terminalState = terminalJobState.get(id);
    if (terminalState) {
      terminalState.stopRequested = true;
    } else {
      terminalJobState.set(id, { stopRequested: true, terminal: false });
    }
    job.stopRequested = true;

    if (!stopEscalationTimers.has(id)) {
      const escalationTimer = setTimeout(() => {
        const activeProcess = runningProcesses.get(id);
        if (!activeProcess) {
          stopEscalationTimers.delete(id);
          return;
        }
        globalLog(registry, `[SYSTEM] escalating stop for ${id} to SIGKILL after ${STOP_ESCALATION_MS}ms`);
        flushPersist(registry);
        try { process.kill(-activeProcess.pid, "SIGKILL"); } catch { activeProcess.kill("SIGKILL"); }
        stopEscalationTimers.delete(id);
      }, STOP_ESCALATION_MS);
      stopEscalationTimers.set(id, escalationTimer);
    }

    globalLog(registry, `[SYSTEM] stop requested ${id}`);
    flushPersist(registry);
    return res.json({ status: "stop_requested", id });
  });

  app.post("/api/jobs/sync", (_req, res) => {
    const changedArtifacts = syncExternalArtifactsToRegistry(registry);
    const proc = discoverActiveExternalProcesses(registry);
    return res.json({
      synced: true,
      changed: changedArtifacts || proc.changed,
      changedArtifacts,
      changedProcesses: proc.changed,
      discoveredProcesses: proc.discovered,
      jobs: registry.jobs.length,
    });
  });

  app.get("/api/processes/discover", (_req, res) => {
    const proc = discoverActiveExternalProcesses(registry);
    return res.json({
      discoveredProcesses: proc.discovered,
      changed: proc.changed,
      jobs: registry.jobs.length,
    });
  });

  app.get("/api/events", (req, res) => {
    const since = Number(req.query.since || 0);
    const events = wsEventHistory.filter((evt) => evt.eventId > (Number.isFinite(since) ? since : 0));
    res.json({
      lastEventId: wsEventSeq,
      events,
      count: events.length,
    });
  });

  // Vite middleware for development
  if (process.env.NODE_ENV !== "production") {
    const vite = await createViteServer({
      server: { middlewareMode: true },
      appType: "spa",
    });
    app.use(vite.middlewares);
  } else {
    const distPath = path.join(process.cwd(), 'dist');
    app.use(express.static(distPath));
    app.get('*', (req, res) => {
      res.sendFile(path.join(distPath, 'index.html'));
    });
  }

  const httpServer = app.listen(PORT, "0.0.0.0", () => {
    console.log(`Server running on http://localhost:${PORT}`);
  });

  // ---- WebSocket server ----
  const wss = new WebSocketServer({ server: httpServer, path: "/ws" });
  const clients = new Set<WebSocketClient>();
  let wsEventSeq = 0;
  const wsEventHistory: Array<{ eventId: number; type: string; payload: unknown; timestamp: string }> = [];
  const WS_EVENT_HISTORY_LIMIT = 2000;

  const makeWsEnvelope = (type: string, payload: unknown) => ({
    eventId: ++wsEventSeq,
    type,
    payload,
    timestamp: isoNow(),
  });

  const sendReplay = (ws: WebSocketClient, sinceEventId: number) => {
    const since = Number.isFinite(sinceEventId) ? sinceEventId : 0;
    const replay = wsEventHistory.filter((evt) => evt.eventId > since);
    ws.send(JSON.stringify({
      type: "replay",
      payload: { sinceEventId: since, events: replay },
      timestamp: isoNow(),
    }));
  };

  const broadcast = (type: string, payload: unknown) => {
    const envelope = makeWsEnvelope(type, payload);
    wsEventHistory.push(envelope);
    if (wsEventHistory.length > WS_EVENT_HISTORY_LIMIT) {
      wsEventHistory.splice(0, wsEventHistory.length - WS_EVENT_HISTORY_LIMIT);
    }

    const message = JSON.stringify(envelope);
    for (const client of clients) {
      if (client.readyState === WebSocketClient.OPEN) {
        client.send(message);
      }
    }
  };

  wss.on("connection", (ws) => {
    clients.add(ws);
    ws.send(
      JSON.stringify({
        type: "status",
        payload: {
          executionMode: registry.executionMode,
          jobsCount: registry.jobs.length,
          lastEventId: wsEventSeq,
        },
        timestamp: isoNow(),
      }),
    );

    ws.on("message", (raw) => {
      try {
        const msg = JSON.parse(raw.toString()) as { type?: string; sinceEventId?: number };
        if (msg.type === "ping") {
          ws.send(JSON.stringify({ type: "pong", payload: { now: isoNow() }, timestamp: isoNow() }));
          return;
        }
        if (msg.type === "request_replay") {
          sendReplay(ws, Number(msg.sinceEventId || 0));
        }
      } catch {
        // ignore malformed client control messages
      }
    });

    ws.on("close", () => clients.delete(ws));
    ws.on("error", () => clients.delete(ws));
  });

  app.get("/api/events", (req, res) => {
    const since = Number(req.query.since || 0);
    const events = wsEventHistory.filter((evt) => evt.eventId > (Number.isFinite(since) ? since : 0));
    res.json({
      lastEventId: wsEventSeq,
      events,
      count: events.length,
    });
  });

  // Telemetry broadcast every 2 seconds
  setInterval(() => {
    if (clients.size === 0) return;
    broadcast("telemetry", buildTelemetryPayload(registry.nodeId));
  }, 2000);

  // Heartbeat ping every 10 seconds to detect half-open connections.
  setInterval(() => {
    if (clients.size === 0) return;
    for (const client of clients) {
      if (client.readyState === WebSocketClient.OPEN) {
        client.send(JSON.stringify({ type: "ping", payload: { now: isoNow() }, timestamp: isoNow() }));
      }
    }
  }, 10000);
}

startServer();