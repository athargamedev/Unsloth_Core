import type { ChildProcessWithoutNullStreams } from "child_process";

// ── Job Types ──────────────────────────────────────────────────────────────

export type ExecutionMode = "local" | "remote";
export type JobStatus = "pending" | "running" | "completed" | "failed" | "stopped";
export type LocalModelSource = "llama-server" | "ollama" | "export" | "job" | "none";

export interface Stage {
  name: string;
  status: "completed" | "running" | "pending" | "failed" | "stopped";
  logs: string[];
}

export interface Job {
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
  error?: string;
  wandbUrl?: string | null;
  runId?: string | null;
}

export interface JobRegistrySnapshot {
  jobs: Job[];
  workflowCount: number;
  autoSyncExternal: boolean;
}

// ── Registry Types ─────────────────────────────────────────────────────────

export interface Registry {
  executionMode: ExecutionMode;
  jobs: Job[];
  logs: string[];
  nodeId: string;
  workflows: Workflow[];
  autoSyncExternal?: boolean;
}

// ── Command Types ──────────────────────────────────────────────────────────

export interface StartCommandPayload {
  commandId?: string;
  type?: string;
  spec?: string;
  preset?: string;
  npcKey?: string;
  options?: Record<string, string | number | boolean | undefined>;
  [key: string]: unknown;
}

export interface CommandDefinition {
  id: string;
  label: string;
  icon: string;
  color: "accent" | "success" | "warning" | "danger" | "default";
  type: string;
  requiredFields: string[];
  build: (payload: StartCommandPayload) => string[];
}

// ── Workflow Types ─────────────────────────────────────────────────────────

export interface WorkflowStep {
  commandId: string;
  status: "pending" | "running" | "completed" | "failed";
  jobId?: string;
  payload: Record<string, unknown>;
}

export interface Workflow {
  id: string;
  name: string;
  spec: string;
  steps: WorkflowStep[];
  currentStep: number;
  overallStatus: "running" | "completed" | "failed";
  createdAt: string;
  finishedAt?: string;
}

// ── Model / Telemetry Types ────────────────────────────────────────────────

export interface LocalModelStatus {
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

export interface GpuTelemetry {
  gpuName: string;
  gpuLoad: number;
  gpuMemoryTotalGB: number;
  gpuMemoryUsedGB: number;
  gpuTemperature: number;
}

export interface TelemetryPayload {
  gpuLoad: number;
  gpuTemperature: number;
  gpuMemoryUsedGB: number;
  gpuMemoryTotalGB: number;
  gpuName: string;
  cpuLoad: number;
  memoryUsedGB: number;
  memoryTotalGB: number;
  platform: string;
  nodeVersion: string;
  nodeId: string;
  timestamp: string;
  networkRxMBps: number;
  networkTxMBps: number;
}

// ── Router Dependencies ────────────────────────────────────────────────────

export interface RouterDependencies {
  registry: Registry;
  runningProcesses: Map<string, ChildProcessWithoutNullStreams>;
  terminalJobState: Map<string, { stopRequested: boolean; terminal: boolean }>;
  stopEscalationTimers: Map<string, NodeJS.Timeout>;
  broadcast: (type: string, payload: unknown) => void;
  commandMap: Map<string, CommandDefinition>;
  repoRoot: string;
  invalidateJobsCache: () => void;
  persistRegistry: (registry: Registry) => void;
  flushPersist: (registry: Registry) => void;
  globalLog: (registry: Registry, line: string) => void;
  defaultStages: () => Stage[];
  isoNow: () => string;
  makeId: () => string;
  unloadGemmaModel: () => void;
  launchJob?: (job: Job) => Job;
  stopJob?: (jobId: string) => boolean;
  readJobLogs?: (jobId: string, maxLines?: number) => string[];
}

// ── Pipeline Types ─────────────────────────────────────────────────────────

export interface PipelineRunRecord {
  ts?: string;
  event?: string;
  run_id?: string;
  npc_key?: string;
  stage?: string;
  technique?: string | null;
  spec_path?: string | null;
  preset?: string | null;
  entrypoint?: string | null;
  frontend_job_id?: string | null;
  pid?: number | null;
  run_dir?: string | null;
  status?: string | null;
  error?: string | null;
  message?: string | null;
  artifacts?: Record<string, unknown>;
  metrics?: Record<string, unknown>;
  [key: string]: unknown;
}

// ── Dataset / Artifact Types ───────────────────────────────────────────────

export interface DatasetInfo {
  npcKey: string;
  technique: string;
  path: string;
  entries: number;
  createdAt: string;
  size: string;
}

export interface RunInfo {
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
}

export interface ExportInfo {
  npcKey: string;
  file: string;
  updatedAt: string;
}

// ── Queue Types ────────────────────────────────────────────────────────────

export interface QueueJob {
  id: string;
  npcKey: string;
  type: string;
  commandId: string;
  commandArgs: string[];
  status: "pending" | "running" | "completed" | "failed" | "stopped";
  progress: number;
  loss: number | null;
  exitCode: number | null;
  error: string | null;
  logs: string[];
  createdAt: string;
  startedAt: string | null;
  finishedAt: string | null;
}

export interface QueueOptions {
  concurrency: number;
  pollIntervalMs: number;
  retryMax: number;
  retryDelayBaseMs: number;
  dbUrl?: string;
}

export interface QueueStats {
  pending: number;
  running: number;
  completed: number;
  failed: number;
  stopped: number;
  total: number;
  activeWorkers: number;
}

export interface JobProcessTracker {
  process: import("child_process").ChildProcessWithoutNullStreams | null;
  stopRequested: boolean;
  terminal: boolean;
}

// ── WebSocket Types ────────────────────────────────────────────────────────

export interface WsEnvelope {
  eventId: number;
  type: string;
  payload: unknown;
  timestamp: string;
}
