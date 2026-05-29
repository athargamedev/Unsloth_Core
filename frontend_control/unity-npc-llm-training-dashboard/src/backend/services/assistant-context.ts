import fs from "node:fs";
import path from "node:path";
import type { Registry } from "../types";

export interface AssistantContextRequest {
  npcKey?: string;
  technique?: string;
  runId?: string;
  jobId?: string;
  message?: string;
}

export interface EvidenceRef {
  source: string;
  path: string;
  excerpt: string;
}

export interface AssistantContextBundle {
  projectGoal: string;
  selectedNpc?: string;
  selectedTechnique?: string;
  activeJobs: Array<Record<string, unknown>>;
  recentJobs: Array<Record<string, unknown>>;
  recentErrors: EvidenceRef[];
  datasetQuality?: unknown;
  qualityFailures?: unknown[];
  exports: string[];
  runs: string[];
  evidence: EvidenceRef[];
}

const readJson = (filePath: string): unknown | null => {
  try {
    if (!fs.existsSync(filePath)) return null;
    return JSON.parse(fs.readFileSync(filePath, "utf8"));
  } catch {
    return null;
  }
};

const tailText = (filePath: string, maxLines = 80): string | null => {
  try {
    if (!fs.existsSync(filePath)) return null;
    return fs.readFileSync(filePath, "utf8").split("\n").slice(-maxLines).join("\n").trim();
  } catch {
    return null;
  }
};

const listFiles = (dir: string, filter: (name: string) => boolean): string[] => {
  try {
    if (!fs.existsSync(dir)) return [];
    return fs.readdirSync(dir).filter(filter).slice(0, 20);
  } catch {
    return [];
  }
};

export function collectAssistantContext(
  repoRoot: string,
  registry: Registry,
  request: AssistantContextRequest,
): AssistantContextBundle {
  const npcKey = request.npcKey || inferNpcKey(request.message) || inferNpcFromJobs(registry);
  const technique = request.technique || "template";
  const evidence: EvidenceRef[] = [];

  const activeJobs = registry.jobs
    .filter((job) => job.status === "running" || job.status === "pending")
    .slice(0, 10)
    .map((job) => ({ id: job.id, name: job.name, type: job.type, commandId: job.commandId, npcKey: job.npcKey, progress: job.progress }));

  const recentJobs = registry.jobs.slice(0, 8).map((job) => ({
    id: job.id,
    name: job.name,
    status: job.status,
    type: job.type,
    commandId: job.commandId,
    npcKey: job.npcKey,
    exitCode: job.exitCode,
    finishedAt: job.finishedAt,
  }));

  const recentErrors: EvidenceRef[] = [];
  for (const job of registry.jobs.slice(0, 8)) {
    const lines = (job.logs || []).filter((line) => /error|exception|traceback|failed|cuda|oom|out of memory/i.test(line)).slice(-5);
    if (lines.length) {
      recentErrors.push({ source: "job-log", path: `/api/jobs/${job.id}/logs`, excerpt: lines.join("\n") });
    }
  }
  for (const line of registry.logs.filter((l) => /error|failed|stopped|exception/i.test(l)).slice(-8)) {
    recentErrors.push({ source: "server-log", path: "/api/logs", excerpt: line });
  }

  let datasetQuality: unknown | undefined;
  let qualityFailures: unknown[] | undefined;
  if (npcKey) {
    const datasetDir = path.join(repoRoot, "subjects", "datasets", npcKey, technique);
    const summaryPath = path.join(datasetDir, "quality_summary.json");
    const failuresPath = path.join(datasetDir, "quality_failures.json");
    datasetQuality = readJson(summaryPath) || undefined;
    const failures = readJson(failuresPath);
    if (Array.isArray(failures)) qualityFailures = failures.slice(0, 8);
    if (datasetQuality) evidence.push({ source: "quality-summary", path: path.relative(repoRoot, summaryPath), excerpt: JSON.stringify(datasetQuality).slice(0, 1200) });
    if (qualityFailures?.length) evidence.push({ source: "quality-failures", path: path.relative(repoRoot, failuresPath), excerpt: JSON.stringify(qualityFailures).slice(0, 1600) });

    const hookCandidates = [
      path.join(repoRoot, "outputs", npcKey, "workflow_hooks.jsonl"),
      path.join(repoRoot, "exports", npcKey, "workflow_hooks.jsonl"),
      path.join(datasetDir, "workflow_hooks.jsonl"),
    ];
    for (const hookPath of hookCandidates) {
      const tail = tailText(hookPath, 20);
      if (tail) evidence.push({ source: "workflow-hooks", path: path.relative(repoRoot, hookPath), excerpt: tail.slice(-1600) });
    }
  }

  const exports = npcKey ? listFiles(path.join(repoRoot, "exports", npcKey), (name) => name.endsWith(".gguf")) : [];
  const runs = npcKey ? listFiles(path.join(repoRoot, "outputs", npcKey, "runs"), () => true) : [];

  return {
    projectGoal: "Create the best local app for Unity developers to generate structured datasets and fine-tune LoRA adapters loaded at runtime in Unity games through LLMUnity.",
    selectedNpc: npcKey,
    selectedTechnique: technique,
    activeJobs,
    recentJobs,
    recentErrors,
    datasetQuality,
    qualityFailures,
    exports,
    runs,
    evidence: [...evidence, ...recentErrors.slice(0, 8)],
  };
}

function inferNpcKey(message?: string): string | undefined {
  const match = message?.match(/\b([a-z][a-z0-9_]+)\b/);
  if (!match) return undefined;
  const value = match[1];
  if (["dataset", "train", "export", "evaluate", "quality", "latest", "workflow"].includes(value)) return undefined;
  return value;
}

function inferNpcFromJobs(registry: Registry): string | undefined {
  return registry.jobs.find((job) => job.npcKey)?.npcKey;
}
