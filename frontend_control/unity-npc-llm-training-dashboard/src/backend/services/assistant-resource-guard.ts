import { execFileSync } from "node:child_process";
import type { Job, Registry } from "../types";

const GPU_HEAVY_TYPES = new Set(["Training", "Evaluation", "Export", "Pipeline"]);
const GPU_HEAVY_COMMANDS = new Set([
  "train",
  "pipeline",
  "dataset-eval",
  "generate-ollama",
  "export",
  "export-adapter",
  "batch-export",
  "evaluate",
  "feedback",
]);

export interface AssistantResourceState {
  canUseLlm: boolean;
  blockedReason: string | null;
  heavyJobs: Array<Pick<Job, "id" | "name" | "type" | "commandId" | "status" | "npcKey">>;
  ollamaModels: string[];
  gpuSnapshot: string | null;
}

export function isGpuHeavyJob(job: Job): boolean {
  if (job.status !== "running" && job.status !== "pending") return false;
  if (GPU_HEAVY_TYPES.has(job.type)) return true;
  if (job.commandId && GPU_HEAVY_COMMANDS.has(job.commandId)) return true;
  const commandText = job.command?.join(" ") || "";
  return /\b(train|dataset-eval|generate-ollama|pipeline|evaluate|batch-export)\b/.test(commandText);
}

export function getAssistantResourceState(registry: Registry): AssistantResourceState {
  const heavyJobs = registry.jobs
    .filter(isGpuHeavyJob)
    .map(({ id, name, type, commandId, status, npcKey }) => ({ id, name, type, commandId, status, npcKey }));

  let ollamaModels: string[] = [];
  try {
    const output = execFileSync("ollama", ["ps"], { encoding: "utf8", timeout: 1500 });
    ollamaModels = output
      .split("\n")
      .slice(1)
      .map((line) => line.trim().split(/\s+/)[0])
      .filter(Boolean);
  } catch {
    ollamaModels = [];
  }

  let gpuSnapshot: string | null = null;
  try {
    gpuSnapshot = execFileSync(
      "nvidia-smi",
      ["--query-gpu=name,memory.used,memory.total,utilization.gpu", "--format=csv,noheader,nounits"],
      { encoding: "utf8", timeout: 1500 },
    ).trim() || null;
  } catch {
    gpuSnapshot = null;
  }

  const blockedReason = heavyJobs.length
    ? `GPU-heavy job active: ${heavyJobs.map((j) => `${j.name} (${j.id})`).join(", ")}`
    : null;

  return {
    canUseLlm: heavyJobs.length === 0,
    blockedReason,
    heavyJobs,
    ollamaModels,
    gpuSnapshot,
  };
}
