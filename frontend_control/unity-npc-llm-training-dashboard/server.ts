import "dotenv/config";
import express from "express";
import fs from "fs";
import os from "os";
import path from "path";
import crypto from "crypto";
import { execFileSync, execSync, spawn, type ChildProcessWithoutNullStreams } from "child_process";
import { createServer as createViteServer } from "vite";
import { WebSocketServer, WebSocket as WebSocketClient } from "ws";
import { computeProgressFromStages, deriveStageStatuses } from "./progressTruth";
import type CodeInterpreter from "@e2b/code-interpreter";

type ExecutionMode = "local" | "remote";
type JobStatus = "pending" | "running" | "completed" | "failed" | "stopped";
type LocalModelSource = "llama-server" | "ollama" | "export" | "job" | "none";

interface LocalModelStatus {
  loaded: boolean;
  source: LocalModelSource;
  displayName: string | null;
  modelId?: string | null;
  ggufPath?: string | null;
  npcKey?: string | null;
  pid?: number | null;
  port?: number | null;
  updatedAt: string;
}

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
  autoSyncExternal?: boolean;
}

interface JobRegistrySnapshot {
  jobs: Job[];
  workflowCount: number;
  autoSyncExternal: boolean;
}

interface StartCommandPayload {
  commandId?: string;
  type?: string;
  spec?: string;
  preset?: string;
  npcKey?: string;
  options?: Record<string, string | number | boolean | undefined>;
  [key: string]: unknown;
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
const serverDir = process.argv[1] ? path.dirname(path.resolve(process.argv[1])) : dashboardRoot;
const findRepoRoot = (): string => {
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

  throw new Error(`Unable to locate Unsloth_Core root. Set UNSLOTH_CORE_ROOT or launch from the dashboard directory. Tried: ${candidates.join(", ")}`);
};
const repoRoot = findRepoRoot();
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
    const registry: Registry = { executionMode: "local", jobs: [], logs: [], nodeId: crypto.randomUUID(), workflows: [], autoSyncExternal: true };
    persistRegistry(registry);
    return registry;
  }

  try {
    const registry = JSON.parse(fs.readFileSync(registryPath, "utf8")) as Registry;
    registry.logs = []; // Global log buffer is transient — cleared on restart
    if (registry.autoSyncExternal === undefined) registry.autoSyncExternal = true;
    if (!registry.nodeId) {
      registry.nodeId = crypto.randomUUID();
      flushPersist(registry);
    }
    return registry;
  } catch {
    const registry: Registry = { executionMode: "local", jobs: [], logs: [], nodeId: crypto.randomUUID(), workflows: [], autoSyncExternal: true };
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

const getJobRegistrySnapshot = (registry: Registry): JobRegistrySnapshot => ({
  jobs: registry.jobs,
  workflowCount: registry.workflows.length,
  autoSyncExternal: registry.autoSyncExternal !== false,
});

const isoNow = () => new Date().toISOString();
const makeId = () => `job_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`;

const noLocalModel = (updatedAt = isoNow()): LocalModelStatus => ({
  loaded: false,
  source: "none",
  displayName: null,
  updatedAt,
});

const tokenizeProcessArgs = (args: string): string[] => {
  const matches = args.match(/(?:[^\s"']+|"[^"]*"|'[^']*')+/g);
  if (!matches) return [];
  return matches.map((token) => token.replace(/^["']|["']$/g, ""));
};

const valueAfterProcessFlag = (tokens: string[], flagNames: string[]): string | null => {
  for (let index = 0; index < tokens.length; index += 1) {
    const token = tokens[index];
    const matchingFlag = flagNames.find((flagName) => token === flagName || token.startsWith(`${flagName}=`));
    if (!matchingFlag) continue;

    if (token.startsWith(`${matchingFlag}=`)) {
      const [, value] = token.split(/=(.*)/s);
      return value || null;
    }

    return tokens[index + 1] || null;
  }

  return null;
};

const inferNpcKeyFromGgufPath = (ggufPath: string): string | null => {
  const segments = path.normalize(ggufPath).split(path.sep);
  const exportsIndex = segments.lastIndexOf("exports");
  if (exportsIndex >= 0 && segments[exportsIndex + 1]) return segments[exportsIndex + 1];
  return null;
};

const displayNameFromGgufPath = (ggufPath: string): string => {
  const basename = path.basename(ggufPath);
  return basename.endsWith(".gguf") ? basename.slice(0, -".gguf".length) : basename;
};

const detectLlamaServerModel = (updatedAt: string): LocalModelStatus | null => {
  try {
    const processList = execSync("ps -eo pid=,args=", { encoding: "utf8", timeout: 1000 });
    const llamaServerLine = processList
      .split("\n")
      .map((line) => line.trim())
      .find((line) => line.includes("llama-server") && /(?:^|\s)(?:-m|--model)(?:\s|=)/.test(line));

    if (!llamaServerLine) return null;

    const [, pidText = "", args = ""] = llamaServerLine.match(/^(\d+)\s+(.*)$/) || [];
    const pid = Number(pidText);
    const tokens = tokenizeProcessArgs(args);
    const ggufPath = valueAfterProcessFlag(tokens, ["-m", "--model"]);
    if (!ggufPath) return null;

    const portText = valueAfterProcessFlag(tokens, ["--port"]);
    const port = portText ? Number(portText) : null;

    return {
      loaded: true,
      source: "llama-server",
      displayName: displayNameFromGgufPath(ggufPath),
      ggufPath,
      npcKey: inferNpcKeyFromGgufPath(ggufPath),
      pid: Number.isFinite(pid) ? pid : null,
      port: port !== null && Number.isFinite(port) ? port : null,
      updatedAt,
    };
  } catch {
    return null;
  }
};

const fetchOllamaModel = async (updatedAt: string): Promise<LocalModelStatus | null> => {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 1000);

  try {
    const response = await fetch("http://127.0.0.1:11434/api/ps", { signal: controller.signal });
    if (!response.ok) return null;

    const payload = (await response.json()) as { models?: Array<{ name?: string; model?: string }> };
    const model = payload.models?.[0];
    const modelId = model?.model || model?.name || null;
    if (!modelId) return null;

    return {
      loaded: true,
      source: "ollama",
      displayName: model.name || modelId,
      modelId,
      updatedAt,
    };
  } catch {
    return null;
  } finally {
    clearTimeout(timeout);
  }
};

const detectLocalModel = async (): Promise<LocalModelStatus> => {
  const updatedAt = isoNow();
  const llamaServerModel = detectLlamaServerModel(updatedAt);
  if (llamaServerModel) return llamaServerModel;

  const ollamaModel = await fetchOllamaModel(updatedAt);
  if (ollamaModel) return ollamaModel;

  return noLocalModel(updatedAt);
};

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
  const raw = (payload as Record<string, unknown>)[key] ?? payload.options?.[key];
  if (typeof raw === "string") return raw;
  if (typeof raw === "number" || typeof raw === "boolean") return String(raw);
  return "";
};

const boolOptionValue = (payload: StartCommandPayload, key: string): boolean => {
  const raw = (payload as Record<string, unknown>)[key] ?? payload.options?.[key];
  if (typeof raw === "boolean") return raw;
  if (typeof raw === "number") return raw !== 0;
  if (typeof raw === "string") return ["1", "true", "yes", "on"].includes(raw.trim().toLowerCase());
  return false;
};

const resolvePayloadPath = (
  payload: StartCommandPayload,
  key: string,
  allowedRoots: string[],
): string => {
  const raw = optionValue(payload, key);
  if (!raw) throw new Error(`${key} is required.`);
  if (path.isAbsolute(raw)) {
    if (!fs.existsSync(raw)) {
      throw new Error(`Invalid ${key}: path not found.`);
    }
    return canonicalizeExistingPath(raw);
  }
  return resolvePathWithinRoots(raw, key, allowedRoots);
};

const parsedSpec = (payload: StartCommandPayload): string => {
  const spec = requireString(payload.spec, "spec");
  return resolvePathWithinRoots(spec, "spec", [path.join(repoRoot, "subjects")]);
};

const parsedDatasetPath = (payload: StartCommandPayload): string => {
  return resolvePathWithinRoots(
    requireString(optionValue(payload, "datasetPath"), "datasetPath"),
    "datasetPath",
    [path.join(repoRoot, "subjects")],
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
  return resolvePayloadPath(payload, "baseline", [path.join(repoRoot, "exports"), path.join(repoRoot, "outputs"), repoRoot]);
};

const parsedCandidate = (payload: StartCommandPayload): string => {
  return resolvePayloadPath(payload, "candidate", [path.join(repoRoot, "exports"), path.join(repoRoot, "outputs"), repoRoot]);
};

const parsedBaseModel = (payload: StartCommandPayload): string => {
  return resolvePayloadPath(payload, "baseModel", [path.join(repoRoot, "exports"), path.join(repoRoot, "outputs"), repoRoot]);
};

const parsedValData = (payload: StartCommandPayload): string => {
  return resolvePayloadPath(payload, "valData", [path.join(repoRoot, "subjects"), repoRoot]);
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
      const model = String(optionValue(payload, "model") || optionValue(payload, "modelId") || "").trim();
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
  {
    id: "dataset-eval",
    label: "Evaluate Dataset Quality",
    icon: "bar-chart",
    color: "warning",
    type: "Dataset",
    requiredFields: ["spec", "options.technique"],
    build: (payload) => ["./ucore", "dataset-eval", parsedSpec(payload), "--technique", sanitizeToken(String(optionValue(payload, "technique") || "template"), "technique")],
  },
  {
    id: "validate-spec",
    label: "Validate Spec",
    icon: "check-circle",
    color: "accent",
    type: "Validation",
    requiredFields: ["spec"],
    build: (payload) => ["./ucore", "validate-spec", parsedSpec(payload), "--generation-ready"],
  },
  {
    id: "validate-config",
    label: "Validate Config",
    icon: "check-circle",
    color: "accent",
    type: "Validation",
    requiredFields: ["spec"],
    build: (payload) => {
      const args = ["./ucore", "validate-config", parsedSpec(payload)];
      const preset = String(payload.preset || "").trim();
      if (preset) args.push("--preset", sanitizeToken(preset, "preset"));
      const dataPath = String(payload.options?.dataPath || "").trim();
      if (dataPath) args.push("--data", resolvePathWithinRoots(dataPath, "dataPath", [repoRoot]));
      if (payload.options?.requireCanonical === true || String(payload.options?.requireCanonical || "").toLowerCase() === "true") {
        args.push("--require-canonical");
      }
      return args;
    },
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
      if (opts.technique) args.push("--technique", String(opts.technique));
      const baseModel = String(opts.baseModel || opts.model || "").trim();
      if (baseModel) args.push("--model", sanitizeToken(baseModel, "model"));
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
      const track = String(optionValue(payload, "track") || "").trim().toLowerCase();
      const wandb = String(optionValue(payload, "wandb") || "").trim().toLowerCase();
      if (preset) cmd.push("--preset", sanitizeToken(preset, "preset"));
      if (technique) cmd.push("--technique", sanitizeToken(technique, "technique"));
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
    build: ({ npcKey }) => ["./ucore", "export-adapter", `outputs/${sanitizeToken(requireString(npcKey, "npcKey"), "npcKey")}`],
  },
  {
    id: "evaluate",
    label: "Evaluate Candidate",
    icon: "bar-chart",
    color: "accent",
    type: "Evaluation",
    requiredFields: ["options.baseline", "options.candidate", "spec"],
    build: (payload) => {
      const command = ["./ucore", "evaluate", "--baseline", parsedBaseline(payload), "--candidate", parsedCandidate(payload), "--spec", parsedSpec(payload)];
      if (optionValue(payload, "valData").trim()) command.push("--val-data", parsedValData(payload));
      if (boolOptionValue(payload, "reportHtml")) command.push("--report-html");
      if (boolOptionValue(payload, "track")) command.push("--track");
      if (boolOptionValue(payload, "judge")) {
        command.push("--judge");
        const judgeModel = optionValue(payload, "judgeModel").trim();
        if (judgeModel) command.push("--judge-model", sanitizeToken(judgeModel, "judgeModel"));
      }
      const baseModel = optionValue(payload, "baseModel").trim();
      if (baseModel) command.push("--base-model", parsedBaseModel(payload));
      const loraWeight = optionValue(payload, "loraWeight").trim();
      if (loraWeight) command.push("--lora-weight", loraWeight);
      const numQuestions = optionValue(payload, "numQuestions").trim();
      if (numQuestions) command.push("--num-questions", numQuestions);
      const feedbackJson = optionValue(payload, "feedbackJson").trim();
      if (feedbackJson) command.push("--feedback-json", resolvePathWithinRoots(feedbackJson, "feedbackJson", [repoRoot]));
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
    requiredFields: [],
    build: ({ options }) => {
      const args = ["./ucore", "deploy"];
      const unityProject = String(options?.unityProject || "").trim();
      if (unityProject) args.push("--unity-project", resolvePathWithinRoots(unityProject, "unityProject", [path.resolve(repoRoot, ".."), repoRoot]));
      if (options?.dryRun === true || options?.dryRun === "true") args.push("--dry-run");
      if (options?.skipExport === true || options?.skipExport === "true") args.push("--skip-export");
      if (options?.exportOnly === true || options?.exportOnly === "true") args.push("--export-only");
      return args;
    },
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
  {
    id: "init",
    label: "Initialize NPC",
    icon: "database",
    color: "accent",
    type: "System",
    requiredFields: ["npcKey"],
    build: ({ npcKey, options }) => {
      const args = ["./ucore", "init", sanitizeToken(requireString(npcKey, "npcKey"), "npcKey")];
      const subject = String(options?.subject || "").trim();
      const name = String(options?.name || "").trim();
      if (subject) args.push("--subject", subject);
      if (name) args.push("--name", name);
      return args;
    },
  },
  {
    id: "plan-batch",
    label: "Generate Colab Notebooks",
    icon: "book-open",
    color: "success",
    type: "Pipeline",
    requiredFields: [],
    build: (payload) => {
      const args = ["./ucore", "plan-batch", "--generate-colab-notebooks"];
      
      const specGlob = String(payload.options?.specGlob || "subjects/NPC_specs/*.json").trim();
      if (specGlob) args.push("--spec-glob", specGlob);

      const presets = String(payload.options?.presets || "fast-3b,premium-3b,premium-8b,safe-any").trim();
      if (presets) args.push("--presets", presets);

      const localVram = String(payload.options?.localVram || "4.0").trim();
      if (localVram) args.push("--local-vram-gb", localVram);

      return args;
    },
  },
  {
    id: "docs-manifest-generate",
    label: "Generate Docs Manifest Dataset",
    icon: "file-text",
    color: "accent",
    type: "Dataset",
    requiredFields: ["spec"],
    build: (payload) => {
      const args = ["./ucore", "generate", parsedSpec(payload), "--technique", "docs"];
      const manifest = String(optionValue(payload, "manifest") || "").trim();
      if (manifest) args.push("--docs-manifest", sanitizeToken(manifest, "manifest"));
      return args;
    },
  },
  {
    id: "feedback",
    label: "Run Feedback Loop",
    icon: "refresh-cw",
    color: "accent",
    type: "Feedback",
    requiredFields: ["feedback_json"],
    build: (payload) => {
      const feedbackJson = resolvePathWithinRoots(
        sanitizeToken(String(requireString(payload.feedback_json, "feedback_json")), "feedback_json"),
        "feedback_json",
        [repoRoot],
      );
      const args = ["./ucore", "feedback", feedbackJson];
      if (payload["dry-run"] === true || String(payload["dry-run"] || "").toLowerCase() === "true") {
        args.push("--dry-run");
      }
      if (payload["skip-gap-detection"] === true || String(payload["skip-gap-detection"] || "").toLowerCase() === "true") {
        args.push("--skip-gap-detection");
      }
      if (payload["auto-retrain"] === true || String(payload["auto-retrain"] || "").toLowerCase() === "true") {
        args.push("--auto-retrain");
      }
      const trainPreset = String(payload["train-preset"] || "").trim();
      if (trainPreset) args.push("--train-preset", sanitizeToken(trainPreset, "train-preset"));
      const baseline = String(payload["baseline"] || "").trim();
      if (baseline) args.push("--baseline", sanitizeToken(baseline, "baseline"));
      const saveGaps = String(payload["save-gaps"] || "").trim();
      if (saveGaps) args.push("--save-gaps", sanitizeToken(saveGaps, "save-gaps"));
      if (payload["json"] === true || String(payload["json"] || "").toLowerCase() === "true") {
        args.push("--json");
      }
      return args;
    },
  },
  {
    id: "generate-ollama",
    label: "Generate Dataset (Ollama Optimized)",
    icon: "database",
    color: "accent",
    type: "Dataset",
    requiredFields: ["spec"],
    build: (payload) => {
      const args = ["./ucore", "generate-ollama", parsedSpec(payload)];
      const model = String(optionValue(payload, "model") || "").trim();
      if (model) args.push("--model", sanitizeToken(model, "model"));
      const batchSize = Number(optionValue(payload, "batchSize"));
      if (batchSize && batchSize !== 4) args.push("--batch-size", String(batchSize));
      const temperature = Number(optionValue(payload, "temperature"));
      if (temperature && temperature !== 0.7) args.push("--temperature", String(temperature));
      const mtRatio = Number(optionValue(payload, "multiTurnRatio"));
      if (mtRatio && mtRatio !== 0.25) args.push("--multi-turn-ratio", String(mtRatio));
      const seed = Number(optionValue(payload, "seed"));
      if (seed && seed !== 42) args.push("--seed", String(seed));
      const url = String(optionValue(payload, "url") || "").trim();
      if (url && url !== "http://localhost:11434") args.push("--url", sanitizeToken(url, "url"));
      const maxRetries = Number(optionValue(payload, "maxRetries"));
      if (maxRetries && maxRetries !== 3) args.push("--max-retries", String(maxRetries));
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
    case "generate-ollama":
    case "dataset-sanitize":
    case "dataset-eval":
    case "validate-spec":
      return 0;
    case "validate-config":
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

const extractNpcKeyFromArgs = (args: string): string | undefined => {
  const match =
    args.match(/subjects\/NPC_specs\/([a-zA-Z0-9_\-]+)\.json/) ??
    args.match(/subjects\/([a-zA-Z0-9_\-]+)\.json/) ??
    args.match(/subjects\/datasets\/([a-zA-Z0-9_\-]+)\//) ??
    args.match(/outputs\/([a-zA-Z0-9_\-]+)\//) ??
    args.match(/exports\/([a-zA-Z0-9_\-]+)\//);
  return match?.[1];
};

const extractFlagValue = (args: string, flag: string): string | undefined => {
  const escapedFlag = flag.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const match = args.match(new RegExp(`(?:^|\\s)${escapedFlag}\\s+([^\\s]+)`));
  return match?.[1];
};

const summarizeExternalProcessName = (pid: number, args: string, commandId: string, type: string, npcKey?: string): string => {
  const details: string[] = [];
  const cleanNpcKey = npcKey ?? extractNpcKeyFromArgs(args);

  if (cleanNpcKey) details.push(cleanNpcKey);

  if (commandId === "train") {
    const preset = extractFlagValue(args, "--preset");
    const technique = extractFlagValue(args, "--technique");
    const model = extractFlagValue(args, "--model") ?? extractFlagValue(args, "--base-model");
    if (preset) details.push(`preset:${preset}`);
    if (technique) details.push(`technique:${technique}`);
    if (model) details.push(`model:${path.basename(model)}`);
  } else if (commandId === "dataset-generate") {
    const technique = extractFlagValue(args, "--technique");
    if (technique) details.push(`technique:${technique}`);
  }

  return `${type} · PID ${pid}${details.length > 0 ? ` · ${details.join(" · ")}` : ""}`;
};

const estimateLiveProgress = (job: Job): number => {
  const base = computeProgressFromStages(job.status, job.stages);
  if (job.status !== "running") return base;

  const activeIndex = job.stages.findIndex((stage) => stage.status === "running");
  if (activeIndex < 0) return base;

  const activeStage = job.stages[activeIndex];
  if (!activeStage) return base;

  const stageFloor = Math.round((activeIndex / Math.max(job.stages.length, 1)) * 100);
  const stageBoost = Math.min(14, Math.max(0, (activeStage.logs.length - 1) * 2));
  return Math.min(99, Math.max(base, stageFloor + 5 + stageBoost));
};

const updateStagesFromTruth = (job: Job) => {
  const activeIndex = job.commandId === "pipeline" ? syncPipelineStageFromLogs(job) : commandStageIndex(job);

  job.stages = deriveStageStatuses(job.stages, job.status, activeIndex, job.commandId === "pipeline");

  if (activeIndex === 3) {
    syncExportStageFromStatusFile(job);
  }

  job.progress = estimateLiveProgress(job);
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

const safeRunId = (value: string): string => {
  if (!/^run_[0-9]{3,}$|^[0-9]{8}_[a-zA-Z0-9_-]+_[0-9]{3,}$/.test(value)) {
    throw new Error("Invalid runId.");
  }
  return value;
};

const safeJobOrRunId = (value: string): string => {
  if (!/^(job_[0-9]+_[a-z0-9]+|ext_train_[a-zA-Z0-9_-]+_.+|run_[0-9]{3,}|[0-9]{8}_[a-zA-Z0-9_-]+_[0-9]{3,})$/.test(value)) {
    throw new Error("Invalid runId.");
  }
  return value;
};

const listNpcRunDirs = (npcKey: string): Array<{ runId: string; runDir: string; layout: "canonical" | "legacy" }> => {
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
};

const resolveTrainingConfigSnapshotPath = (npcKey: string): string | null => {
  const candidates = [
    path.join(repoRoot, "outputs", npcKey, "best", "config_snapshot.yaml"),
    path.join(repoRoot, "outputs", npcKey, "latest", "config_snapshot.yaml"),
  ];
  for (const candidate of candidates) {
    if (fs.existsSync(candidate)) return candidate;
  }

  const runs = listNpcRunDirs(npcKey)
    .sort((a, b) => fs.statSync(b.runDir).mtimeMs - fs.statSync(a.runDir).mtimeMs);
  for (const run of runs) {
    const configPath = path.join(run.runDir, "config_snapshot.yaml");
    if (fs.existsSync(configPath)) return configPath;
  }

  return null;
};

const findRunDirById = (requestedId: string, registry: Registry): { runId: string; runDir: string } | null => {
  const id = safeJobOrRunId(requestedId);
  const job = registry.jobs.find((item) => item.id === id);
  const possibleRunIds = new Set<string>([id]);

  if (job) {
    for (const line of job.logs) {
      const match = line.match(/outputs\/([a-zA-Z0-9_-]+)\/(?:runs\/)?([^/\s]+)(?:\/|\s|$)/);
      if (match?.[2]) possibleRunIds.add(match[2]);
    }
    const outputLine = job.logs.find((line) => line.includes("Output:"));
    const outputMatch = outputLine?.match(/outputs\/([a-zA-Z0-9_-]+)\/(?:runs\/)?([^/\s]+)/);
    if (outputMatch?.[2]) possibleRunIds.add(outputMatch[2]);
  }

  const npcKeys = job?.npcKey ? [job.npcKey] : fs.existsSync(path.join(repoRoot, "outputs")) ? fs.readdirSync(path.join(repoRoot, "outputs")) : [];
  for (const npcKey of npcKeys) {
    const npcDir = path.join(repoRoot, "outputs", npcKey);
    if (!fs.existsSync(npcDir) || !fs.statSync(npcDir).isDirectory()) continue;
    for (const run of listNpcRunDirs(npcKey)) {
      if (possibleRunIds.has(run.runId)) return { runId: run.runId, runDir: run.runDir };
    }
  }

  // Final fallback for active training: try the latest run directory for the NPC.
  // Only return runs created AFTER the job started to avoid showing stale data from previous completed runs.
  if (job?.status === "running" && job.npcKey) {
    const jobCreatedMs = new Date(job.createdAt).getTime() || 0;
    const runs = listNpcRunDirs(job.npcKey)
      .filter((run) => fs.statSync(run.runDir).mtimeMs >= jobCreatedMs)
      .sort((a, b) => fs.statSync(b.runDir).mtimeMs - fs.statSync(a.runDir).mtimeMs);
    if (runs.length > 0) return { runId: runs[0].runId, runDir: runs[0].runDir };
  }

  return null;
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
  return true;
};

const syncExternalArtifactsToRegistry = (registry: Registry) => {
  if (registry.autoSyncExternal === false) return false;
  let changed = false;

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

  const outputsRoot = path.join(repoRoot, "outputs");
  if (fs.existsSync(outputsRoot)) {
    for (const npcKey of fs.readdirSync(outputsRoot)) {
      const npcPath = path.join(outputsRoot, npcKey);
      if (!fs.statSync(npcPath).isDirectory()) continue;

      for (const { runId, runDir, layout } of listNpcRunDirs(npcKey)) {
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
          const raw = manifestPath.endsWith(".json") ? JSON.parse(fs.readFileSync(manifestPath, "utf8")) as {
            created_at?: string;
            preset?: string;
            model_id?: string;
            results?: { training_loss?: number };
            train_loss?: number;
          } : {};
          if (raw.created_at) {
            const normalized = new Date(raw.created_at);
            if (!Number.isNaN(normalized.getTime())) createdAt = normalized.toISOString();
          }
          preset = raw.preset || "";
          modelId = raw.model_id || "";
          loss = typeof raw.results?.training_loss === "number" ? raw.results.training_loss : typeof raw.train_loss === "number" ? raw.train_loss : null;
        } catch {
          // ignore malformed manifests and still import by file mtime
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
          logs: [
            `[EXTERNAL] run artifact detected: ${path.relative(repoRoot, manifestPath)}`,
            `[EXTERNAL] run layout=${layout}`,
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

  if (changed) flushPersist(registry);
  return changed;
};

const normalizeLegacyExternalProcessNames = (registry: Registry) => {
  let changed = false;
  for (const job of registry.jobs) {
    if (!job.id.startsWith("ext_proc_")) continue;
    const pid = Number(job.id.replace("ext_proc_", ""));
    const args = job.command?.[1];
    if (!Number.isFinite(pid) || typeof args !== "string" || args.trim() === "") continue;

    const inferredNpcKey = extractNpcKeyFromArgs(args);
    if (!job.npcKey && inferredNpcKey) {
      job.npcKey = inferredNpcKey;
      changed = true;
    }

    const nextName = summarizeExternalProcessName(pid, args, job.commandId ?? "pipeline", job.type, job.npcKey);
    if (job.name !== nextName) {
      job.name = nextName;
      changed = true;
    }
  }
  if (changed) flushPersist(registry);
  return changed;
};

const discoverActiveExternalProcesses = (registry: Registry) => {
  if (registry.autoSyncExternal === false) return { changed: false, discovered: 0 };
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
      let needsUpdate = false;
      const nextName = summarizeExternalProcessName(pid, args, commandId, type, npcKey);
      if (existing.status !== "running") {
        existing.status = "running";
        existing.finishedAt = undefined;
        existing.exitCode = undefined;
        existing.terminalReason = "external_detected";
        needsUpdate = true;
      }
      // Re-classify existing entry if commandId/type changed (e.g. after server restart)
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
      if (existing.name !== nextName) {
        existing.name = nextName;
        needsUpdate = true;
      }
      if (needsUpdate) {
        appendStageLog(existing, `[EXTERNAL][PID ${pid}] Process still running (re-classified as ${type})`);
        changed = true;
      }
      continue;
    }

    const job: Job = {
      id,
      name: summarizeExternalProcessName(pid, args, commandId, type, npcKey),
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
  normalizeLegacyExternalProcessNames(registry);
  syncExternalArtifactsToRegistry(registry);
  discoverActiveExternalProcesses(registry);

  // ── Jobs cache: avoid filesystem scan on every /api/jobs request ──
  const CACHE_TTL_MS = 2000;
  let jobsCache: { jobs: Job[]; timestamp: number } | null = null;

  const invalidateJobsCache = () => { jobsCache = null; };

  const refreshJobsCacheIfStale = () => {
    const now = Date.now();
    if (jobsCache && now - jobsCache.timestamp < CACHE_TTL_MS) return jobsCache.jobs;
    syncExternalArtifactsToRegistry(registry);
    discoverActiveExternalProcesses(registry);
    jobsCache = { jobs: registry.jobs, timestamp: now };
    return jobsCache.jobs;
  };

  // Background sync: keep external artifacts and processes in sync without blocking API requests
  setInterval(() => {
    const changedArtifacts = syncExternalArtifactsToRegistry(registry);
    const procResult = discoverActiveExternalProcesses(registry);
    if (changedArtifacts || procResult.changed) {
      invalidateJobsCache();
    }
  }, 3000);

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
    const datasetsRoot = path.join(repoRoot, "subjects", "datasets");
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
    const specsDir = path.join(repoRoot, "subjects", "NPC_specs");
    if (!fs.existsSync(specsDir)) return [];
    return fs.readdirSync(specsDir)
      .filter((f) => f.endsWith(".json"))
      .map((file) => ({ id: file.replace(/\.json$/, ""), path: `subjects/NPC_specs/${file}` }));
  };

  const parseRunSnapshotScalar = (raw: string): string | number | boolean | null => {
  const value = raw.trim();
  if (!value || value === "null" || value === "~") return null;
  if (value === "true") return true;
  if (value === "false") return false;
  if (/^-?\d+(?:\.\d+)?(?:e[+-]?\d+)?$/i.test(value)) return Number(value);
  return value;
};

const readRunMetadata = (runDir: string) => {
  const metadata: Record<string, any> = {
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
      const metrics = JSON.parse(fs.readFileSync(metricsPath, "utf8"));
      Object.assign(metadata, {
        loss: typeof metrics.train_loss === "number" ? metrics.train_loss : (typeof metrics.loss === "number" ? metrics.loss : null),
        trainRuntime: typeof metrics.train_runtime === "number" ? metrics.train_runtime : null,
        trainSamplesPerSecond: typeof metrics.train_samples_per_second === "number" ? metrics.train_samples_per_second : null,
        trainStepsPerSecond: typeof metrics.train_steps_per_second === "number" ? metrics.train_steps_per_second : null,
        epoch: typeof metrics.epoch === "number" ? metrics.epoch : null,
      });
    } catch {
      // ignore malformed metrics
    }
  }

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
};

const listRuns = () => {
    const outputsRoot = path.join(repoRoot, "outputs");
    if (!fs.existsSync(outputsRoot)) return [];
    const entries: Array<{
      id: string;
      npcKey: string;
      runId: string;
      path: string;
      updatedAt: string;
      layout: string;
      model?: string | null;
      datasetPath?: string | null;
      technique?: string | null;
      loss?: number | null;
      trainRuntime?: number | null;
      trainSamplesPerSecond?: number | null;
      trainStepsPerSecond?: number | null;
      epoch?: number | null;
      batchSize?: number | null;
      epochs?: number | null;
      learningRate?: number | null;
      loraRank?: number | null;
      loraAlpha?: number | null;
      wandbEnabled?: boolean | null;
      hasConfigSnapshot?: boolean;
      hasAdapter?: boolean;
      hasTensorBoard?: boolean;
    }> = [];
    for (const npcKey of fs.readdirSync(outputsRoot)) {
      const npcPath = path.join(outputsRoot, npcKey);
      if (!fs.statSync(npcPath).isDirectory()) continue;
      for (const run of listNpcRunDirs(npcKey)) {
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
          trainSamplesPerSecond: typeof metadata.trainSamplesPerSecond === "number" ? metadata.trainSamplesPerSecond : null,
          trainStepsPerSecond: typeof metadata.trainStepsPerSecond === "number" ? metadata.trainStepsPerSecond : null,
          epoch: typeof metadata.epoch === "number" ? metadata.epoch : null,
          batchSize: typeof metadata["training.batch_size"] === "number" ? metadata["training.batch_size"] : null,
          epochs: typeof metadata["training.num_epochs"] === "number" ? metadata["training.num_epochs"] : null,
          learningRate: typeof metadata["training.learning_rate"] === "number" ? metadata["training.learning_rate"] : null,
          loraRank: typeof metadata["lora.r"] === "number" ? metadata["lora.r"] : null,
          loraAlpha: typeof metadata["lora.alpha"] === "number" ? metadata["lora.alpha"] : null,
          wandbEnabled: typeof metadata["wandb.enabled"] === "boolean" ? metadata["wandb.enabled"] : null,
          hasConfigSnapshot: Boolean(metadata.hasConfigSnapshot),
          hasAdapter: Boolean(metadata.hasAdapter),
          hasTensorBoard: Boolean(metadata.hasTensorBoard),
        });
      }
    }
    return entries.sort((a, b) => b.updatedAt.localeCompare(a.updatedAt));
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
    const jobs = refreshJobsCacheIfStale();
    res.json(jobs);
  });
  app.get("/api/jobs/state", (_req, res) => {
    const jobs = refreshJobsCacheIfStale();
    res.json({
      jobs,
      workflowCount: registry.workflows.length,
      autoSyncExternal: registry.autoSyncExternal !== false,
    } satisfies JobRegistrySnapshot);
  });
  app.get("/api/logs", (_req, res) => res.json(registry.logs));
  app.post("/api/logs/clear", (_req, res) => {
    registry.logs.length = 0;
    flushPersist(registry);
    broadcast("logs_cleared", { clearedAt: new Date().toISOString() });
    res.json({ success: true });
  });

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

  app.get("/api/manifests", (_req, res) => {
    const corporaRoot = path.join(repoRoot, "docs", "corpora");
    if (!fs.existsSync(corporaRoot)) return res.json([]);
    try {
      const manifests = fs.readdirSync(corporaRoot)
        .filter((f) => f.endsWith(".json"))
        .map((file) => {
          const filePath = path.join(corporaRoot, file);
          let manifestData: Record<string, unknown> = {};
          try {
            manifestData = JSON.parse(fs.readFileSync(filePath, "utf8"));
          } catch {
            // skip malformed
          }
          const sources = (manifestData.sources as Array<{ path: string; kind?: string; questions?: unknown[] }>) || [];
          return {
            name: file,
            path: `docs/corpora/${file}`,
            manifest_name: manifestData.manifest_name || file.replace(".json", ""),
            description: manifestData.description || "",
            version: manifestData.version || "",
            source_count: sources.length,
            total_questions: sources.reduce((sum, s) => sum + (Array.isArray(s.questions) ? s.questions.length : 0), 0),
            lastModified: fs.statSync(filePath).mtime.toISOString(),
          };
        })
        .sort((a, b) => b.lastModified.localeCompare(a.lastModified));
      return res.json(manifests);
    } catch (err) {
      return res.status(500).json({ error: "Failed to list manifests" });
    }
  });

  app.get("/api/manifests/:name", (req, res) => {
    const name = String(req.params.name || "").replace(/\.json$/i, "") + ".json";
    const safePath = path.join(repoRoot, "docs", "corpora", name);
    if (!safePath.startsWith(path.join(repoRoot, "docs", "corpora"))) {
      return res.status(400).json({ error: "Invalid manifest name." });
    }
    if (!fs.existsSync(safePath)) {
      return res.status(404).json({ error: `Manifest not found: ${name}` });
    }
    try {
      const content = JSON.parse(fs.readFileSync(safePath, "utf8"));
      const sources = (content.sources || []).map((source: { path: string; kind?: string; questions?: unknown[] }) => {
        const sourcePath = path.join(repoRoot, source.path);
        const exists = fs.existsSync(sourcePath);
        return {
          ...source,
          exists,
          doc_size: exists ? `${Math.max(1, Math.round(fs.statSync(sourcePath).size / 1024))}KB` : "N/A",
        };
      });
      return res.json({ ...content, sources, manifest_path: `docs/corpora/${name}` });
    } catch (err) {
      return res.status(500).json({ error: "Failed to load manifest" });
    }
  });

  // --- Dataset Quality API endpoints ---

  app.get("/api/datasets/quality-summary", (_req, res) => {
    const datasetsDir = path.join(repoRoot, "subjects", "datasets");
    if (!fs.existsSync(datasetsDir)) return res.json([]);
    try {
      const results: Array<{ npcKey: string; technique: string; path: string; summary: Record<string, unknown> }> = [];
      const npcDirs = fs.readdirSync(datasetsDir);
      for (const npcKey of npcDirs) {
        const npcDir = path.join(datasetsDir, npcKey);
        if (!fs.statSync(npcDir).isDirectory()) continue;
        const techniqueDirs = fs.readdirSync(npcDir);
        for (const technique of techniqueDirs) {
          const summaryPath = path.join(npcDir, technique, "quality_summary.json");
          if (fs.existsSync(summaryPath)) {
            try {
              const summary = JSON.parse(fs.readFileSync(summaryPath, "utf8"));
              results.push({ npcKey, technique, path: `subjects/datasets/${npcKey}/${technique}/quality_summary.json`, summary });
            } catch {
              // skip malformed
            }
          }
        }
      }
      return res.json(results);
    } catch (err) {
      return res.status(500).json({ error: "Failed to list quality summaries" });
    }
  });

  app.get("/api/datasets/quality-summary/:npcKey/:technique", (req, res) => {
    const npcKey = String(req.params.npcKey || "").replace(/\.\./g, "");
    const technique = String(req.params.technique || "").replace(/\.\./g, "");
    if (!npcKey || !technique) {
      return res.status(400).json({ error: "npcKey and technique are required" });
    }
    const summaryPath = path.join(repoRoot, "subjects", "datasets", npcKey, technique, "quality_summary.json");
    if (!summaryPath.startsWith(path.join(repoRoot, "subjects", "datasets"))) {
      return res.status(400).json({ error: "Invalid path" });
    }
    if (!fs.existsSync(summaryPath)) {
      return res.status(404).json({ error: `Quality summary not found for ${npcKey}/${technique}` });
    }
    try {
      const summary = JSON.parse(fs.readFileSync(summaryPath, "utf8"));
      return res.json(summary);
    } catch (err) {
      return res.status(500).json({ error: "Failed to load quality summary" });
    }
  });

  app.get("/api/datasets/quality-failures/:npcKey/:technique", (req, res) => {
    const npcKey = String(req.params.npcKey || "").replace(/\.\./g, "");
    const technique = String(req.params.technique || "").replace(/\.\./g, "");
    if (!npcKey || !technique) {
      return res.status(400).json({ error: "npcKey and technique are required" });
    }

    // Try to load summary first to get the failures_path
    const summaryPath = path.join(repoRoot, "subjects", "datasets", npcKey, technique, "quality_summary.json");
    let failuresPath: string | null = null;

    if (fs.existsSync(summaryPath)) {
      try {
        const summary = JSON.parse(fs.readFileSync(summaryPath, "utf8"));
        if (summary.failures_path) {
          const candidatePath = path.join(repoRoot, summary.failures_path);
          if (candidatePath.startsWith(repoRoot) && fs.existsSync(candidatePath)) {
            failuresPath = candidatePath;
          }
        }
      } catch {
        // fall through to default path
      }
    }

    // Fallback to default path
    if (!failuresPath) {
      failuresPath = path.join(repoRoot, "subjects", "datasets", npcKey, technique, "quality_failures.json");
    }

    if (!failuresPath.startsWith(path.join(repoRoot, "subjects", "datasets"))) {
      return res.status(400).json({ error: "Invalid path" });
    }

    if (!fs.existsSync(failuresPath)) {
      return res.status(404).json({ error: `Quality failures not found for ${npcKey}/${technique}` });
    }

    try {
      const failures = JSON.parse(fs.readFileSync(failuresPath, "utf8"));
      return res.json(failures);
    } catch (err) {
      return res.status(500).json({ error: "Failed to load quality failures" });
    }
  });

  app.get("/api/colab/notebooks", (_req, res) => {
    const colabDir = path.join(repoRoot, "colab", "outputs");
    if (!fs.existsSync(colabDir)) return res.json([]);
    try {
      const files = fs.readdirSync(colabDir)
        .filter((f) => f.endsWith(".ipynb"))
        .map((f) => {
          const filePath = path.join(colabDir, f);
          const stat = fs.statSync(filePath);
          
          let npcKey = "";
          let preset = "";
          try {
            const content = JSON.parse(fs.readFileSync(filePath, "utf8"));
            const meta = content.metadata?.unsloth_core || {};
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
        .sort((a, b) => b.lastModified.localeCompare(a.lastModified));
      return res.json(files);
    } catch (err) {
      return res.status(500).json({ error: "Failed to list Colab notebooks" });
    }
  });

  app.get("/api/colab/download", (req, res) => {
    const requestedPath = String(req.query.path || "");
    if (!requestedPath.startsWith("colab/outputs/") || requestedPath.includes("..")) {
      return res.status(400).json({ error: "Invalid notebook path." });
    }
    const absolutePath = path.resolve(repoRoot, requestedPath);
    if (!fs.existsSync(absolutePath) || !fs.statSync(absolutePath).isFile()) {
      return res.status(404).json({ error: "Notebook file not found." });
    }
    return res.download(absolutePath);
  });

  const onyxBaseUrl = process.env.ONYX_BASE_URL || "http://localhost";
  const onyxApiKey = process.env.ONYX_API_KEY;

  async function syncLiveStateToOnyx() {
    const activeSubjects = listSubjects();
    const activeJobs = registry.jobs.filter(j => j.status === "running");
    
    const text = `CURRENT WORKSPACE STATE (Runtime data):
- Total NPCs (Subjects): ${activeSubjects.length} (${activeSubjects.map(s => s.id).join(", ")})
- Active Running Jobs: ${activeJobs.length}
- Available Datasets: ${listDatasets().length}
- Exported Models (GGUF): ${listExports().length}

ACTIONABLE COMMANDS:
Whenever you suggest a command, format it clearly using markdown code blocks starting with ./ucore.
The user can execute these commands directly from your interface.`;

    const payload = {
      document: {
        id: "unsloth_core:live_state",
        semantic_identifier: "Live Workspace State",
        title: "Live Workspace State (NPCs, Jobs, Datasets)",
        sections: [
          {
            text: text,
            link: "http://localhost:3100"
          }
        ],
        source: "ingestion_api",
        metadata: {
          category: "system_state",
          tags: ["live-state", "system", "workspace"]
        },
        doc_updated_at: new Date().toISOString(),
        from_ingestion_api: true
      }
    };

    try {
      await fetch(`${onyxBaseUrl}/api/onyx-api/ingestion`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(onyxApiKey ? { Authorization: `Bearer ${onyxApiKey}` } : {}),
        },
        body: JSON.stringify(payload)
      });
    } catch (err) {
      // Ignore background sync errors
    }
  }

  // Run the sync every 15 seconds to keep Onyx updated
  setInterval(syncLiveStateToOnyx, 15000);
  syncLiveStateToOnyx();

  app.post("/api/assistant", async (req, res) => {
    const message = typeof req.body?.message === "string" ? req.body.message.trim() : "";
    if (!message) return res.status(400).json({ error: "message is required" });

    try {
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 60_000);
      let response: Response;

      try {
        response = await fetch(`${onyxBaseUrl}/api/chat/send-chat-message`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            ...(onyxApiKey ? { Authorization: `Bearer ${onyxApiKey}` } : {}),
          },
          body: JSON.stringify({
            message: message,
            persona_id: 0, // Search Agent
          }),
          signal: controller.signal,
        });
      } finally {
        clearTimeout(timeout);
      }

      if (!response.ok) {
        const text = await response.text();
        return res.status(502).json({ error: `Onyx request failed: ${text}` });
      }

      const data = await response.json() as { answer?: string };
      return res.json({ content: data.answer || "No assistant response generated." });
    } catch (error) {
      if (error instanceof Error && error.name === "AbortError") {
        return res.status(504).json({ error: "Assistant request timed out after 60 seconds.", timeout: true });
      }
      const messageText = error instanceof Error ? error.message : "Assistant request failed.";
      if (messageText.includes("ECONNREFUSED") || messageText.includes("fetch failed")) {
        return res.json({
          content: "**Onyx Server is not running.** Ensure the Onyx backend is available, then try again.",
        });
      }
      return res.status(500).json({ error: messageText });
    }
  });

  const unloadGemmaModel = () => {
    try {
      const result = require("child_process").execSync("ollama ps", { encoding: "utf8", timeout: 5000 });
      const lines = result.trim().split("\n");
      // Skip header line, extract first column (NAME) from remaining lines
      for (let i = 1; i < lines.length; i++) {
        const line = lines[i].trim();
        if (!line) continue;
        const modelName = line.split(/\s+/)[0];
        if (!modelName) continue;
        try {
          require("child_process").execSync(`ollama stop ${modelName}`, { stdio: "ignore", timeout: 5000 });
          globalLog(registry, `[SYSTEM] Unloaded ${modelName} to free GPU memory`);
        } catch {
          globalLog(registry, `[SYSTEM] Failed to unload ${modelName}, continuing`);
        }
      }
    } catch {
      globalLog(registry, "[SYSTEM] Could not query Ollama running models");
    }
  };

  const unloadAssistantModel = () => {
    try {
      require("child_process").execSync("ollama stop llama3.1:latest", { stdio: "ignore", timeout: 5000 });
      globalLog(registry, "[SYSTEM] Unloaded llama3.1:latest to free GPU memory");
    } catch {
      // ignore
    }
  };

  app.post("/api/assistant/unload", (_req, res) => {
    unloadAssistantModel();
    res.json({ success: true, message: "Model unloaded" });
  });

  app.post("/api/assistant/load", async (_req, res) => {
    try {
      // Send empty generate request just to load it into VRAM
      await fetch("http://127.0.0.1:11434/api/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ model: "llama3.1:latest", keep_alive: "5m" })
      });
      res.json({ success: true, message: "Model loading requested" });
    } catch (e) {
      res.status(500).json({ error: "Failed to load model" });
    }
  });

  app.post("/api/assistant/execute", (req, res) => {
    const commandStr = typeof req.body?.command === "string" ? req.body.command.trim() : "";
    if (!commandStr || !commandStr.startsWith("./ucore")) {
      return res.status(400).json({ error: "Only ./ucore commands are allowed for execution." });
    }

    try {
      const tokens = tokenizeProcessArgs(commandStr);
      // Basic security: don't allow shell injection or path traversal beyond what tokenize handles
      
      const job: Job = {
        id: makeId(),
        name: `Assistant: ${commandStr.length > 40 ? commandStr.slice(0, 37) + "..." : commandStr}`,
        type: "Assistant",
        status: "running",
        progress: 5,
        loss: null,
        createdAt: isoNow(),
        startedAt: isoNow(),
        command: tokens,
        stages: defaultStages(),
        logs: [],
      };
      
      const startedJob = launchJob(job);
      res.json(startedJob);
    } catch (error) {
      res.status(400).json({ error: error instanceof Error ? error.message : "Failed to execute assistant command." });
    }
  });

  app.get("/api/dataset/:npcKey/:technique", (req, res) => {
    const { npcKey, technique } = req.params;
    const n = Math.min(Math.max(parseInt(String(req.query.n || "10"), 10) || 10, 1), 100);

    // Security: reject path traversal
    if (npcKey.includes("..") || technique.includes("..")) {
      return res.status(400).json({ error: "Invalid path" });
    }

    const trainPath = path.join(repoRoot, "subjects", "datasets", npcKey, technique, "train.jsonl");
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

    // Scan eval/reports/ (legacy structured per-NPC dirs)
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

    // Also scan eval/results/ for HTML comparison reports
    const resultsDir = path.join(evalRoot, "results");
    if (fs.existsSync(resultsDir)) {
      const resultFiles = fs.readdirSync(resultsDir)
        .filter((f) => f.endsWith(".html") || f.endsWith(".htm"))
        .map((f) => ({
          name: f,
          path: `eval/results/${f}`,
        }));
      if (resultFiles.length > 0) {
        // Add under "results" pseudo-NPC key, filtered to only HTML reports
        reports.push({ npcKey: "comparison-reports", files: resultFiles });
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

  app.get("/api/eval-reports/file", (req, res) => {
    const requestedPath = String(req.query.path || "");
    if (requestedPath.includes("..")) {
      return res.status(400).json({ error: "Invalid report path." });
    }
    // Allow serving from both eval/reports/ and eval/results/
    const allowed = [
      path.resolve(repoRoot, "eval", "reports") + path.sep,
      path.resolve(repoRoot, "eval", "results") + path.sep,
    ];
    const absolutePath = path.resolve(repoRoot, requestedPath);
    const isAllowed = allowed.some((prefix) => absolutePath.startsWith(prefix));
    if (!isAllowed) {
      return res.status(400).json({ error: "Report path is outside allowed eval directories." });
    }
    if (!fs.existsSync(absolutePath) || !fs.statSync(absolutePath).isFile()) {
      return res.status(404).json({ error: "Report file not found." });
    }

    return res.sendFile(absolutePath);
  });

  // --- Pipeline State API ---

  app.get("/api/pipeline-state", (_req, res) => {
    const statePath = path.join(repoRoot, "eval", "results", "pipeline_state.json");
    if (!fs.existsSync(statePath)) {
      return res.json({});
    }
    try {
      const raw = fs.readFileSync(statePath, "utf8");
      return res.json(JSON.parse(raw));
    } catch {
      return res.status(500).json({ error: "Failed to parse pipeline_state.json" });
    }
  });

  // --- Feedback Results API ---

  app.get("/api/feedback-results", (_req, res) => {
    const feedbackDir = path.join(repoRoot, "eval", "results", "feedback");
    if (!fs.existsSync(feedbackDir)) {
      return res.json([]);
    }
    try {
      const files = fs.readdirSync(feedbackDir)
        .filter((f) => f.endsWith(".json"))
        .map((f) => ({
          name: f,
          path: `eval/results/feedback/${f}`,
          lastModified: fs.statSync(path.join(feedbackDir, f)).mtimeMs,
        }))
        .sort((a, b) => b.lastModified - a.lastModified);
      return res.json(files);
    } catch {
      return res.status(500).json({ error: "Failed to list feedback results" });
    }
  });

  app.get("/api/feedback-result/file", (req, res) => {
    const requestedPath = String(req.query.path || "");
    if (!requestedPath.startsWith("eval/results/feedback/") || requestedPath.includes("..")) {
      return res.status(400).json({ error: "Invalid feedback result path." });
    }
    const absolutePath = path.resolve(repoRoot, requestedPath);
    if (!fs.existsSync(absolutePath) || !fs.statSync(absolutePath).isFile()) {
      return res.status(404).json({ error: "Feedback result file not found." });
    }
    try {
      const raw = fs.readFileSync(absolutePath, "utf8");
      return res.json(JSON.parse(raw));
    } catch {
      return res.status(500).json({ error: "Failed to parse feedback result file." });
    }
  });

  app.get("/api/run/:npcKey/:runId", (req, res) => {
    const { npcKey, runId } = req.params;

    if (!/^[a-zA-Z0-9_-]+$/.test(npcKey)) {
      return res.status(400).json({ error: "Invalid path" });
    }

    try {
      safeRunId(runId);
    } catch (error) {
      return res.status(400).json({ error: error instanceof Error ? error.message : "Invalid runId" });
    }

    const runPath = listNpcRunDirs(npcKey).find((run) => run.runId === runId)?.runDir || "";
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
  app.get("/api/system/status", async (_req, res) => {
    res.json({
      executionMode: registry.executionMode,
      runningJobs: registry.jobs.filter((job) => job.status === "running").length,
      totalJobs: registry.jobs.length,
      repoRoot,
      localModel: await detectLocalModel(),
      timestamp: isoNow(),
    });
  });

  app.get("/api/health", (_req, res) => {
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
    const npcKey = typeof req.query.npcKey === "string" ? req.query.npcKey.trim() : "";
    if (!runId) return res.json({ runId: "", scalars: {}, error: "runId query parameter is required" });

    let resolvedRun: { runId: string; runDir: string } | null = null;
    try {
      if (npcKey) {
        const run = listNpcRunDirs(npcKey).find((item) => item.runId === runId);
        resolvedRun = run ? { runId: run.runId, runDir: run.runDir } : null;
      } else {
        resolvedRun = findRunDirById(runId, registry);
      }
    } catch (error) {
      const msg = error instanceof Error ? error.message : "Invalid runId";
      return res.json({ runId, scalars: {}, error: msg });
    }

    if (!resolvedRun) {
      return res.json({ runId, scalars: {}, error: `Run directory not found for ${npcKey ? `${npcKey}/${runId}` : runId}` });
    }

    try {
      const result = execFileSync(
        "python",
        ["scripts/evaluation/tb_reader.py", "--run-dir", resolvedRun.runDir],
        { cwd: repoRoot, encoding: "utf8", timeout: 10000 },
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
      const cmd = ["./ucore", "deploy"];
      if (dryRun) cmd.push("--dry-run");
      if (req.body?.unityProject) {
        cmd.push("--unity-project", resolvePathWithinRoots(String(req.body.unityProject), "unityProject", [path.resolve(repoRoot, ".."), repoRoot]));
      }
      if (req.body?.skipExport === true) cmd.push("--skip-export");
      if (req.body?.exportOnly === true) cmd.push("--export-only");
      const result = execFileSync(cmd[0], cmd.slice(1), {
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
      const npcKey = spec.replace(/^subjects\//, "").replace(/\.json$/, "");
      const technique = String(req.body?.technique || (npcKey === "workflow_assistant" ? "docs" : "template")).trim();
      if (!spec) return res.status(400).json({ error: "spec is required" });

      const isWorkflowTool = npcKey === "workflow_assistant";
      const workflowId = `wf_${Date.now()}`;

      // Resolve model ID for the export step — auto-detect from spec or training output config
      let exportModelId = String(req.body?.options?.baseModel || "");
      if (!exportModelId) {
        try {
          const specPath = path.join(repoRoot, "subjects", `${npcKey}.json`);
          if (fs.existsSync(specPath)) {
            const specData = JSON.parse(fs.readFileSync(specPath, "utf8")) as Record<string, unknown>;
            exportModelId = String(
              specData.model || specData.model_id || (specData.llm as Record<string, unknown> || {}).model_name || "",
            );
          }
        } catch (e) { console.warn("[WORKFLOW] Failed to parse subject spec JSON:", e); }
      }
      if (!exportModelId) {
        try {
          const bestConfigPath = resolveTrainingConfigSnapshotPath(npcKey);
          if (bestConfigPath) {
            const content = fs.readFileSync(bestConfigPath, "utf8");
            const modelMatch = content.match(/^model:\s*(.+)$/m);
            if (modelMatch) exportModelId = modelMatch[1].trim();
          }
        } catch (e) { console.warn("[WORKFLOW] Failed to parse training config snapshot:", e); }
      }

      const steps: WorkflowStep[] = [
        { commandId: "dataset-generate", status: "pending", payload: { commandId: "dataset-generate", type: "Dataset", spec, options: { technique } } },
        { commandId: "dataset-sanitize", status: "pending", payload: { commandId: "dataset-sanitize", type: "Dataset", spec, options: { datasetPath: `subjects/datasets/${npcKey}/${technique}/train.jsonl` } } },
      ];

      if (isWorkflowTool) {
        steps.push({
          commandId: "validate-config",
          status: "pending",
          payload: {
            commandId: "validate-config",
            type: "Validation",
            spec,
            preset,
            options: {
              dataPath: `subjects/datasets/${npcKey}/${technique}/train_clean.jsonl`,
              requireCanonical: true,
            },
          },
        });
      } else {
        steps.push({ commandId: "train", status: "pending", payload: { commandId: "train", type: "Training", spec, preset, npcKey, options: { ...req.body?.options || {}, technique } } });
      }

      // Only add export step for real NPCs, not the workflow assistant tool.
      if (!isWorkflowTool) {
        if (exportModelId) {
          steps.push({ commandId: "export", status: "pending", payload: { commandId: "export", type: "Export", npcKey, options: { modelId: exportModelId } } });
        } else {
          globalLog(registry, `[WORKFLOW] export step skipped: no baseModel provided and model could not be auto-detected from spec or training config`);
        }
      }

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
      registry.logs.length = 0; // Clear global log buffer — start fresh
      globalLog(registry, `[WORKFLOW] starting ${workflowId} step 1/${steps.length}: ${command.join(" ")}`);
      persistRegistry(registry);
      broadcast("job_update", { id: job.id, status: job.status, loss: job.loss, progress: job.progress });

      unloadGemmaModel();
      const child = spawn(command[0], command.slice(1), { cwd: repoRoot, shell: false, detached: true });
      runningProcesses.set(job.id, child);
      terminalJobState.set(job.id, { stopRequested: false, terminal: false });

      const consume = (chunk: Buffer, source: "stdout" | "stderr") => {
        const lines = chunk.toString().split("\n").map((l) => l.trim()).filter(Boolean);
        for (const line of lines) {
          const prefixed = `[${source.toUpperCase()}][${job.id}] ${line}`;
          const previousProgress = job.progress;
          job.logs.push(prefixed);
          job.logs = job.logs.slice(-MAX_LOG_LINES);
          appendStageLog(job, prefixed);
          globalLog(registry, prefixed);
          const parsedLoss = parseLoss(line);
          if (parsedLoss !== null) {
            job.loss = parsedLoss;
          }
          updateStagesFromTruth(job);
          if (job.progress !== previousProgress || parsedLoss !== null) {
            broadcast("job_update", { id: job.id, status: job.status, loss: job.loss, progress: job.progress });
          }
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
        invalidateJobsCache();
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

              unloadGemmaModel();
              const nextChild = spawn(nextCommand[0], nextCommand.slice(1), { cwd: repoRoot, shell: false, detached: true });
              runningProcesses.set(nextJob.id, nextChild);
              terminalJobState.set(nextJob.id, { stopRequested: false, terminal: false });

              const nextConsume = (chunk: Buffer, source: "stdout" | "stderr") => {
                const lines = chunk.toString().split("\n").map((l) => l.trim()).filter(Boolean);
                for (const line of lines) {
                  const prefixed = `[${source.toUpperCase()}][${nextJob.id}] ${line}`;
                  const previousProgress = nextJob.progress;
                  nextJob.logs.push(prefixed);
                  nextJob.logs = nextJob.logs.slice(-MAX_LOG_LINES);
                  appendStageLog(nextJob, prefixed);
                  globalLog(registry, prefixed);
                  const parsedLoss = parseLoss(line);
                  if (parsedLoss !== null) {
                    nextJob.loss = parsedLoss;
                  }
                  updateStagesFromTruth(nextJob);
                  if (nextJob.progress !== previousProgress || parsedLoss !== null) {
                    broadcast("job_update", { id: nextJob.id, status: nextJob.status, loss: nextJob.loss, progress: nextJob.progress });
                  }
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
                invalidateJobsCache();
                broadcast("job_update", { id: nextJob.id, status: nextJob.status, loss: nextJob.loss, progress: nextJob.progress });
              });
            } catch (chainErr) {
              globalLog(registry, `[WORKFLOW] chaining failed: ${chainErr instanceof Error ? chainErr.message : String(chainErr)}`);
              workflow.overallStatus = "failed";
              workflow.finishedAt = isoNow();
              flushPersist(registry);
              invalidateJobsCache();
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
        spec: { type: "string", required: true, default: "subjects/NPC_specs/history_guide.json", description: "Subject spec path" },
        "options.technique": { type: "string", required: false, default: "ollama", enum: ["template", "docs", "ollama", "openai", "anthropic"] },
      },
      "dataset-sanitize": {
        "options.datasetPath": { type: "string", required: true, default: "subjects/datasets/history_guide/ollama/train.jsonl", description: "Train dataset path" },
      },
      train: {
        spec: { type: "string", required: true, default: "subjects/NPC_specs/history_guide.json" },
        preset: { type: "string", required: false, default: "fast-3b", ...(presetOptions.length ? { enum: presetOptions } : {}) },
        "options.learningRate": { type: "string", required: false, default: "2e-4" },
        "options.batchSize": { type: "number", required: false, default: 1 },
        "options.epochs": { type: "number", required: false, default: 3 },
        "options.rank": { type: "number", required: false, default: 16 },
        "options.alpha": { type: "number", required: false, default: 32 },
        "options.baseModel": { type: "string", required: false, default: "unsloth/Llama-3.2-3B-Instruct-bnb-4bit" },
        "options.technique": { type: "string", required: false, default: "ollama", enum: ["template", "docs", "ollama", "openai", "anthropic"] },
        "options.wandb": { type: "boolean", required: false, default: false },
      },
      pipeline: {
        spec: { type: "string", required: true, default: "subjects/NPC_specs/history_guide.json" },
        preset: { type: "string", required: false, default: "fast-3b", ...(presetOptions.length ? { enum: presetOptions } : {}) },
        "options.technique": { type: "string", required: false, default: "ollama", enum: ["template", "docs", "ollama", "openai", "anthropic"] },
        "options.track": { type: "boolean", required: false, default: false },
        "options.wandb": { type: "boolean", required: false, default: false },
      },
      export: {
        npcKey: { type: "string", required: true, default: "history_guide" },
        "options.modelId": { type: "string", required: true, default: "unsloth/Llama-3.2-3B-Instruct-bnb-4bit" },
      },
      "export-adapter": {
        npcKey: { type: "string", required: true, default: "history_guide" },
      },
      evaluate: {
        spec: { type: "string", required: true, default: "subjects/NPC_specs/history_guide.json" },
        "options.baseline": { type: "string", required: true, default: "exports/history_guide/history_guide-lora-f16.gguf" },
        "options.candidate": { type: "string", required: true, default: "exports/history_guide/history_guide-lora-f16.gguf" },
        "options.valData": { type: "string", required: false, default: "" },
      },
      smoke: {
        spec: { type: "string", required: true, default: "subjects/NPC_specs/history_guide.json" },
        "options.modelPath": { type: "string", required: true, default: "exports/history_guide/history_guide-lora-f16.gguf" },
      },
      deploy: {
        "options.unityProject": { type: "string", required: false, default: "" },
        "options.dryRun": { type: "boolean", required: false, default: true },
        "options.skipExport": { type: "boolean", required: false, default: false },
        "options.exportOnly": { type: "boolean", required: false, default: false },
      },
      "supabase-check": {
        npcKey: { type: "string", required: true, default: "history_guide" },
        "options.playerId": { type: "string", required: false, default: "" },
      },
      init: {
        npcKey: { type: "string", required: true, default: "new_npc_key", description: "NPC Key (snake_case)" },
        "options.subject": { type: "string", required: false, default: "", description: "NPC Subject" },
        "options.name": { type: "string", required: false, default: "", description: "NPC Display Name" },
      },
      "validate-spec": {
        spec: { type: "string", required: true, default: "subjects/NPC_specs/history_guide.json", description: "Subject spec path" },
      },
      "dataset-eval": {
        spec: { type: "string", required: true, default: "subjects/NPC_specs/history_guide.json", description: "Subject spec path" },
        "options.technique": { type: "string", required: true, default: "ollama", enum: ["template", "docs", "ollama", "openai", "anthropic"], description: "Dataset generation technique" },
      },
      "docs-manifest-generate": {
        spec: { type: "string", required: true, default: "subjects/NPC_specs/history_guide.json", description: "Subject spec path" },
        manifest: { type: "string", required: false, default: "docs/corpora/workflow_assistant_docs.json", description: "Corpus manifest path" },
        "options.technique": { type: "string", required: false, default: "docs", enum: ["docs"] },
      },
      "generate-ollama": {
        spec: { type: "string", required: true, default: "subjects/NPC_specs/history_guide.json", description: "Subject spec path" },
        "options.model": { type: "string", required: false, default: "llama3.2:3b", description: "Ollama model name" },
        "options.batchSize": { type: "number", required: false, default: 4, description: "Concurrent generation tasks" },
        "options.temperature": { type: "number", required: false, default: 0.7, description: "Generation temperature (0.0-1.0)" },
        "options.multiTurnRatio": { type: "number", required: false, default: 0.25, description: "Fraction of multi-turn dialogues" },
        "options.seed": { type: "number", required: false, default: 42, description: "Random seed for reproducibility" },
        "options.url": { type: "string", required: false, default: "http://localhost:11434", description: "Ollama server URL" },
        "options.maxRetries": { type: "number", required: false, default: 3, description: "Max retries per generation" },
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
      
      const startedJob = launchJob(job);
      res.json(startedJob);
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
    invalidateJobsCache();
    return res.json({ status: "stop_requested", id });
  });

  app.delete("/api/jobs/:id", (req, res) => {
    const { id } = req.params;
    const index = registry.jobs.findIndex((j) => j.id === id);
    if (index === -1) return res.status(404).json({ error: "Job not found" });
    const job = registry.jobs[index];
    if (job.status === "running") return res.status(409).json({ error: "Cannot delete a running job" });

    registry.jobs.splice(index, 1);
    invalidateJobsCache();
    globalLog(registry, `[SYSTEM] dismissed job ${id}`);
    flushPersist(registry);
    broadcast("job_deleted", { id });
    return res.json({ success: true });
  });

  app.post("/api/jobs/clear", (_req, res) => {
    const running = registry.jobs.filter((job) => job.status === "running");
    if (running.length > 0) {
      return res.status(409).json({ error: "Cannot clear while jobs are running", running: running.map((job) => job.id) });
    }

    registry.jobs = [];
    registry.workflows = [];
    registry.logs = [];
    registry.autoSyncExternal = false;
    invalidateJobsCache();
    flushPersist(registry);
    broadcast("logs_cleared", { clearedAt: new Date().toISOString() });
    broadcast("job_update", { cleared: true, jobs: 0, autoSyncExternal: false });
    return res.json({ success: true, cleared: true });
  });

  app.post("/api/jobs/sync", (req, res) => {
    const force = Boolean((req.body as { force?: boolean } | undefined)?.force);
    if (force) {
      registry.autoSyncExternal = true;
    }
    const changedArtifacts = syncExternalArtifactsToRegistry(registry);
    const proc = discoverActiveExternalProcesses(registry);
    invalidateJobsCache();
    if (force || changedArtifacts || proc.changed) {
      broadcast("job_update", {
        synced: true,
        force,
        jobs: registry.jobs.length,
        autoSyncExternal: registry.autoSyncExternal !== false,
      });
    }
    return res.json({
      synced: true,
      force,
      changed: changedArtifacts || proc.changed,
      changedArtifacts,
      changedProcesses: proc.changed,
      discoveredProcesses: proc.discovered,
      jobs: registry.jobs.length,
      autoSyncExternal: registry.autoSyncExternal !== false,
      workflowCount: registry.workflows.length,
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

  // Helper for launching jobs (shared by /api/commands/start and /api/assistant/execute)
  const launchJob = (job: Job) => {
    updateStagesFromTruth(job);
    registry.logs.length = 0; // Clear global log buffer — start fresh
    registry.jobs.unshift(job);
    invalidateJobsCache();
    globalLog(registry, `[SYSTEM] starting ${job.id}: ${job.command.join(" ")}`);
    persistRegistry(registry);
    broadcast("job_update", { id: job.id, status: job.status, loss: job.loss, progress: job.progress });

    unloadGemmaModel();
    const child = spawn(job.command[0], job.command.slice(1), { cwd: repoRoot, shell: false, detached: true });
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

        const wandbMatch = line.match(/https:\/\/wandb\.ai\/[-a-zA-Z0-9./_?=&#%~]+\/runs\/([a-z0-9]+)/i);
        if (wandbMatch) {
          const wandbUrl = wandbMatch[0];
          if (!job.wandbUrl) {
            job.wandbUrl = wandbUrl;
            broadcast("job_update", { id: job.id, status: job.status, loss: job.loss, progress: job.progress, wandbUrl });
          }
        }

        const parsedLossValue = parseLoss(line);
        if (parsedLossValue !== null) {
          job.loss = parsedLossValue;
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
      updateStagesFromTruth(job);
      globalLog(registry, `[SYSTEM] job ${job.id} ${job.status} (exit ${code})`);
      flushPersist(registry);
      invalidateJobsCache();
      broadcast("job_update", { id: job.id, status: job.status, loss: job.loss, progress: job.progress });
    });
    
    return job;
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


