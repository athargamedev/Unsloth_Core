import type { AssistantContextBundle } from "./assistant-context";
import type { AssistantResourceState } from "./assistant-resource-guard";

export const WORKFLOW_ASSISTANT_SYSTEM_PROMPT = `You are the Unsloth_Core Workflow Assistant, an operational copilot for local Unity NPC LoRA production.

Mission: help Unity developers create high-quality structured datasets, fine-tune LoRA adapters, export GGUF adapters, evaluate them, and deploy them through LLMUnity.

You are not an NPC character. Do not roleplay as an NPC. Do not invent project state.
Use only provided context, retrieved docs, logs, metrics, command schemas, and explicit user input.

Priorities:
1. Protect local resources. Never recommend running assistant LLM work concurrently with training, dataset-eval, Ollama generation, export, or llama-server eval.
2. Preserve quality gates. Do not weaken dataset thresholds or bypass gates unless the user explicitly requests development bypass.
3. Prefer exact ./ucore commands and dashboard actions.
4. Always cite evidence when diagnosing logs/results.
5. When uncertain, ask for the missing artifact instead of guessing.
6. Focus on the goal: best local workflow for Unity developers generating NPC datasets and runtime LoRA adapters for LLMUnity.

Response style: concise, actionable, exact file paths/flags. For diagnostics use: Findings, Evidence, Recommendation, Next Command.`;

export function buildAssistantUserPrompt(message: string, context: AssistantContextBundle, resources: AssistantResourceState): string {
  return JSON.stringify({
    user_message: message,
    resource_state: resources,
    context,
    instruction: "Answer using only this context. If proposing commands, mark them as Proposed only and require confirmation.",
  }, null, 2);
}

export function deterministicAssistantReply(message: string, context: AssistantContextBundle, resources: AssistantResourceState): string {
  const lines: string[] = [];
  if (!resources.canUseLlm) {
    lines.push(`**Assistant LLM paused:** ${resources.blockedReason}`);
    lines.push("I can still summarize available state without loading a local model.");
  }

  lines.push("## Current State");
  lines.push(`- Selected NPC: \`${context.selectedNpc || "unknown"}\``);
  lines.push(`- Technique: \`${context.selectedTechnique || "template"}\``);
  lines.push(`- Active jobs: ${context.activeJobs.length}`);
  lines.push(`- Recent jobs tracked: ${context.recentJobs.length}`);
  if (context.exports.length) lines.push(`- Exports: ${context.exports.map((f) => `\`${f}\``).join(", ")}`);
  if (context.runs.length) lines.push(`- Runs: ${context.runs.slice(0, 5).map((f) => `\`${f}\``).join(", ")}`);

  if (context.recentErrors.length) {
    lines.push("\n## Recent Error Evidence");
    for (const err of context.recentErrors.slice(0, 3)) {
      lines.push(`- ${err.path}: \`${err.excerpt.replace(/`/g, "'").slice(0, 240)}\``);
    }
  }

  if (context.datasetQuality) {
    const summary = context.datasetQuality as Record<string, unknown>;
    lines.push("\n## Dataset Quality");
    lines.push(`- Status/pass rate: \`${String(summary.status || "unknown")}\` / \`${String(summary.pass_rate ?? "n/a")}\``);
    lines.push(`- Total/failed: \`${String(summary.total ?? "n/a")}\` / \`${String(summary.failed ?? "n/a")}\``);
  }

  lines.push("\n## Recommendation");
  if (/fail|error|why|diagnos/i.test(message) && context.recentErrors.length) {
    lines.push("Inspect the cited job log first, then retry only the failed stage after fixing the root cause.");
  } else if (/quality|dataset/i.test(message)) {
    lines.push("Run or inspect the dataset quality gate before training. Fix generation prompts, primers, or failed rows; do not lower thresholds.");
  } else if (/train/i.test(message)) {
    lines.push("Before training, ensure `train_clean.jsonl` exists and has a fresh passing `quality_summary.json` for the exact dataset hash.");
  } else {
    lines.push("Select an NPC/run/job context, then ask for a targeted diagnosis or comparison.");
  }

  return lines.join("\n");
}
