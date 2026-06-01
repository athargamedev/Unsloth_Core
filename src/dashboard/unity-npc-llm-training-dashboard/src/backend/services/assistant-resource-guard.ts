import { execFile } from "node:child_process";
import { promisify } from "node:util";
import type { Job, Registry } from "../types";

const execFileAsync = promisify(execFile);

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

export async function getAssistantResourceState(registry: Registry): Promise<AssistantResourceState> {
  const heavyJobs = registry.jobs
    .filter(isGpuHeavyJob)
    .map(({ id, name, type, commandId, status, npcKey }) => ({ id, name, type, commandId, status, npcKey }));

  // Run ollama ps and nvidia-smi concurrently (non-blocking)
  const [ollamaResult, gpuResult] = await Promise.allSettled([
    execFileAsync("ollama", ["ps"], { encoding: "utf8", timeout: 1500 }),
    execFileAsync(
      "nvidia-smi",
      ["--query-gpu=name,memory.used,memory.total,utilization.gpu", "--format=csv,noheader,nounits"],
      { encoding: "utf8", timeout: 1500 },
    ),
  ]);

  const ollamaModels = ollamaResult.status === "fulfilled"
    ? ollamaResult.value.stdout
        .split("\n")
        .slice(1)
        .map((line) => line.trim().split(/\s+/)[0])
        .filter(Boolean)
    : [];

  const gpuSnapshot = gpuResult.status === "fulfilled"
    ? gpuResult.value.stdout.trim() || null
    : null;

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
