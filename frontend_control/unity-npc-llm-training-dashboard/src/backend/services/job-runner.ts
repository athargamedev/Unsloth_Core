import { spawn, type ChildProcessWithoutNullStreams } from "child_process";
import fs from "fs";
import os from "os";
import path from "path";
import type { Job, Registry, Stage, JobStatus } from "../types";
import { computeProgressFromStages, deriveStageStatuses } from "../../../progressTruth";

// ── Constants ──────────────────────────────────────────────────────────────

const MAX_LOG_LINES = 2000;
const STOP_ESCALATION_MS = 10_000;

// ── Process Tracking ───────────────────────────────────────────────────────

export const runningProcesses = new Map<string, ChildProcessWithoutNullStreams>();
export const terminalJobState = new Map<string, { stopRequested: boolean; terminal: boolean }>();
export const stopEscalationTimers = new Map<string, NodeJS.Timeout>();

// ── Logging Helpers (injected) ─────────────────────────────────────────────

export interface RunnerDeps {
  registry: Registry;
  repoRoot: string;
  broadcast: (type: string, payload: unknown) => void;
  globalLog: (registry: Registry, line: string) => void;
  persistRegistry: (registry: Registry) => void;
  flushPersist: (registry: Registry) => void;
  invalidateJobsCache: () => void;
  unloadGemmaModel: () => void;
  isoNow: () => string;
  makeId: () => string;
  defaultStages: () => Stage[];
  writeJobLog: (jobId: string, line: string) => void;
}

// ── Stage Helpers ──────────────────────────────────────────────────────────

export const defaultStages = (): Stage[] => [
  { name: "Dataset Prep", status: "pending", logs: [] },
  { name: "Training", status: "pending", logs: [] },
  { name: "Evaluation", status: "pending", logs: [] },
  { name: "Export", status: "pending", logs: [] },
  { name: "Feedback", status: "pending", logs: [] },
];

export function isoNow(): string {
  return new Date().toISOString();
}

export function makeId(): string {
  return `job_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`;
}

export function parseLoss(line: string): number | null {
  const match = line.match(/loss[:=]\s*([0-9]*\.?[0-9]+)/i);
  if (!match) return null;
  return Number(match[1]);
}

/**
 * Determines which stage index a command maps to.
 */
export function commandStageIndex(job: Job): number {
  switch (job.commandId) {
    case "dataset-generate":
    case "generate-ollama":
    case "dataset-sanitize":
    case "dataset-eval":
    case "validate-spec":
    case "docs-manifest-generate":
    case "init":
    case "audit":
      return 0;
    case "validate-config":
    case "train":
      return 1;
    case "evaluate":
    case "smoke":
    case "compare-runs":
    case "track":
    case "quick-eval":
      return 2;
    case "feedback":
      return 4;
    case "export":
    case "export-adapter":
    case "deploy":
    case "supabase-check":
    case "plan-batch":
    case "export-resume":
    case "batch-export":
      return 3;
    case "pipeline":
      return 0;
    default:
      return 0;
  }
}

/**
 * Scans logs for [stage] markers to sync pipeline progress.
 */
export function syncPipelineStageFromLogs(job: Job): number {
  for (let i = job.logs.length - 1; i >= 0; i -= 1) {
    const line = job.logs[i].toLowerCase();
    const marker = line.match(/\[stage\]\s+(dataset|training|evaluation|export|feedback|complete)/i);
    if (!marker) continue;
    const stage = marker[1];
    if (stage === "dataset") return 0;
    if (stage === "training") return 1;
    if (stage === "evaluation") return 2;
    if (stage === "export") return 3;
    if (stage === "feedback" || stage === "complete") return 4;
  }
  return 0;
}

/**
 * Estimates live progress percentage from stage activity.
 */
export function estimateLiveProgress(job: Job): number {
  const base = computeProgressFromStages(job.status, job.stages);
  if (job.status !== "running") return base;

  const activeIndex = job.stages.findIndex((stage) => stage.status === "running");
  if (activeIndex < 0) return base;

  const activeStage = job.stages[activeIndex];
  if (!activeStage) return base;

  const stageFloor = Math.round((activeIndex / Math.max(job.stages.length, 1)) * 100);
  const stageBoost = Math.min(14, Math.max(0, (activeStage.logs.length - 1) * 2));
  return Math.min(99, Math.max(base, stageFloor + 5 + stageBoost));
}

/**
 * Updates job stages, progress, and export status based on current state.
 */
export function updateStagesFromTruth(job: Job): void {
  const activeIndex = job.commandId === "pipeline" ? syncPipelineStageFromLogs(job) : commandStageIndex(job);
  job.stages = deriveStageStatuses(job.stages, job.status, activeIndex, job.commandId === "pipeline");
  job.progress = estimateLiveProgress(job);
}

/**
 * Appends a log message to the active stage.
 */
export function appendStageLog(job: Job, message: string): void {
  const activeIndex = job.commandId === "pipeline" ? syncPipelineStageFromLogs(job) : commandStageIndex(job);
  const stage = job.stages[activeIndex] ?? job.stages[job.stages.length - 1];
  if (!stage) return;
  stage.logs.push(message);
  stage.logs = stage.logs.slice(-50);
}

/**
 * Launches a job as a child process. Tracks output, parses loss, broadcasts updates.
 */
export function launchJob(job: Job, deps: RunnerDeps): Job {
  const {
    registry,
    repoRoot,
    broadcast,
    globalLog,
    flushPersist,
    invalidateJobsCache,
    unloadGemmaModel,
    persistRegistry,
    writeJobLog,
  } = deps;

  updateStagesFromTruth(job);
  registry.logs.length = 0;
  registry.jobs.unshift(job);
  invalidateJobsCache();
  globalLog(registry, `[SYSTEM] starting ${job.id}: ${job.command.join(" ")}`);
  persistRegistry(registry);
  broadcast("job_update", { id: job.id, status: job.status, loss: job.loss, progress: job.progress });

  unloadGemmaModel();
  const child = spawn(job.command[0], job.command.slice(1), {
    cwd: repoRoot,
    shell: false,
    detached: true,
    env: { ...process.env, WORKFLOW_HOOKS_PATH: process.env.WORKFLOW_HOOKS_PATH || "" },
  });
  runningProcesses.set(job.id, child);
  terminalJobState.set(job.id, { stopRequested: false, terminal: false });

  const consume = (chunk: Buffer, source: "stdout" | "stderr") => {
    const lines = chunk
      .toString()
      .split("\n")
      .map((line) => line.trim())
      .filter(Boolean);
    for (const line of lines) {
      const prefixed = `[${source.toUpperCase()}][${job.id}] ${line}`;
      job.logs.push(prefixed);
      job.logs = job.logs.slice(-MAX_LOG_LINES);
      writeJobLog(job.id, line);
      appendStageLog(job, prefixed);
      globalLog(registry, prefixed);

      const wandbMatch = line.match(
        /https:\/\/wandb\.ai\/[-a-zA-Z0-9./_?=&#%~]+\/runs\/([a-z0-9]+)/i,
      );
      if (wandbMatch) {
        const wandbUrl = wandbMatch[0];
        if (!job.wandbUrl) {
          job.wandbUrl = wandbUrl;
          broadcast("job_update", {
            id: job.id,
            status: job.status,
            loss: job.loss,
            progress: job.progress,
            wandbUrl,
          });
        }
      }

      const parsedLossValue = parseLoss(line);
      if (parsedLossValue !== null) {
        job.loss = parsedLossValue;
        broadcast("job_update", {
          id: job.id,
          status: job.status,
          loss: job.loss,
          progress: job.progress,
        });
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
      job.status = "stopped" as JobStatus;
      job.terminalReason = "user_requested_stop";
    } else {
      job.status = (code === 0 ? "completed" : "failed") as JobStatus;
    }
    updateStagesFromTruth(job);
    globalLog(registry, `[SYSTEM] job ${job.id} ${job.status} (exit ${code})`);
    flushPersist(registry);
    invalidateJobsCache();
    broadcast("job_update", {
      id: job.id,
      status: job.status,
      loss: job.loss,
      progress: job.progress,
    });
  });

  return job;
}

/**
 * Stops a running job by PID. Sends SIGTERM first, escalates to SIGKILL after STOP_ESCALATION_MS.
 */
export function stopJob(jobId: string): boolean {
  const proc = runningProcesses.get(jobId);
  if (!proc || !proc.pid) return false;

  try {
    process.kill(-proc.pid, "SIGTERM");
  } catch {
    proc.kill("SIGTERM");
  }

  const terminalState = terminalJobState.get(jobId);
  if (terminalState) {
    terminalState.stopRequested = true;
  } else {
    terminalJobState.set(jobId, { stopRequested: true, terminal: false });
  }

  if (!stopEscalationTimers.has(jobId)) {
    const timer = setTimeout(() => {
      const activeProcess = runningProcesses.get(jobId);
      if (!activeProcess) {
        stopEscalationTimers.delete(jobId);
        return;
      }
      try {
        process.kill(-activeProcess.pid, "SIGKILL");
      } catch {
        activeProcess.kill("SIGKILL");
      }
      stopEscalationTimers.delete(jobId);
    }, STOP_ESCALATION_MS);
    stopEscalationTimers.set(jobId, timer);
  }

  return true;
}
