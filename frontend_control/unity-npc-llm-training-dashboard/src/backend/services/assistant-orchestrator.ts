import fs from "node:fs";
import path from "node:path";
import type { Registry } from "../types";
import { collectAssistantContext, type AssistantContextRequest } from "./assistant-context";
import { getAssistantResourceState } from "./assistant-resource-guard";
import { WORKFLOW_ASSISTANT_SYSTEM_PROMPT, buildAssistantUserPrompt, deterministicAssistantReply } from "./assistant-prompts";

export interface AssistantConfigProfile {
  provider: "ollama";
  model: string;
  num_ctx?: number;
  num_gpu?: number;
  num_parallel?: number;
  keep_alive?: string | number;
}

export interface AssistantChatResult {
  content: string;
  usedLlm: boolean;
  blockedReason: string | null;
  model: string;
  context: ReturnType<typeof collectAssistantContext>;
  resourceState: ReturnType<typeof getAssistantResourceState>;
}

const DEFAULT_PROFILE: AssistantConfigProfile = {
  provider: "ollama",
  model: process.env.WORKFLOW_ASSISTANT_MODEL || "qwen3:latest",
  num_ctx: 8192,
  num_parallel: 1,
  keep_alive: "0s",
};

export function loadAssistantProfile(repoRoot: string, requestedProfile?: string): AssistantConfigProfile {
  const configPath = path.join(repoRoot, "frontend_control", "unity-npc-llm-training-dashboard", "workflow_assistant", "assistant_config.json");
  try {
    if (!fs.existsSync(configPath)) return DEFAULT_PROFILE;
    const config = JSON.parse(fs.readFileSync(configPath, "utf8")) as {
      defaultProfile?: string;
      profiles?: Record<string, AssistantConfigProfile>;
    };
    const profileName = requestedProfile || config.defaultProfile || "balanced_idle";
    return config.profiles?.[profileName] || DEFAULT_PROFILE;
  } catch {
    return DEFAULT_PROFILE;
  }
}

export async function runAssistantChat(
  repoRoot: string,
  registry: Registry,
  request: AssistantContextRequest & { history?: unknown[]; profile?: string },
): Promise<AssistantChatResult> {
  const resources = getAssistantResourceState(registry);
  const context = collectAssistantContext(repoRoot, registry, request);
  const profile = loadAssistantProfile(repoRoot, request.profile);

  if (!resources.canUseLlm) {
    return {
      content: deterministicAssistantReply(request.message || "", context, resources),
      usedLlm: false,
      blockedReason: resources.blockedReason,
      model: profile.model,
      context,
      resourceState: resources,
    };
  }

  try {
    const content = await callOllama(profile, request.message || "", context, resources);
    return {
      content,
      usedLlm: true,
      blockedReason: null,
      model: profile.model,
      context,
      resourceState: resources,
    };
  } catch (error) {
    const fallback = deterministicAssistantReply(request.message || "", context, resources);
    return {
      content: `${fallback}\n\n_Assistant model unavailable: ${error instanceof Error ? error.message : "unknown error"}_`,
      usedLlm: false,
      blockedReason: null,
      model: profile.model,
      context,
      resourceState: resources,
    };
  }
}

async function callOllama(
  profile: AssistantConfigProfile,
  message: string,
  context: ReturnType<typeof collectAssistantContext>,
  resources: ReturnType<typeof getAssistantResourceState>,
): Promise<string> {
  const response = await fetch(`${process.env.OLLAMA_BASE_URL || "http://localhost:11434"}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      model: profile.model,
      messages: [
        { role: "system", content: WORKFLOW_ASSISTANT_SYSTEM_PROMPT },
        { role: "user", content: buildAssistantUserPrompt(message, context, resources) },
      ],
      stream: false,
      keep_alive: profile.keep_alive ?? "0s",
      options: {
        num_ctx: profile.num_ctx ?? 8192,
        num_gpu: profile.num_gpu,
        num_parallel: profile.num_parallel ?? 1,
        temperature: 0.2,
      },
    }),
  });
  if (!response.ok) {
    throw new Error(`Ollama chat failed (${response.status})`);
  }
  const payload = (await response.json()) as { message?: { content?: string }; response?: string };
  const content = payload.message?.content || payload.response || "";
  if (!content.trim()) throw new Error("empty Ollama response");
  return content;
}

export async function setAssistantModelLoaded(repoRoot: string, load: boolean, profileName?: string): Promise<{ model: string; ok: boolean }> {
  const profile = loadAssistantProfile(repoRoot, profileName);
  const response = await fetch(`${process.env.OLLAMA_BASE_URL || "http://localhost:11434"}/api/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      model: profile.model,
      prompt: "",
      stream: false,
      keep_alive: load ? "5m" : 0,
      options: { num_ctx: profile.num_ctx ?? 8192, num_gpu: profile.num_gpu, num_parallel: 1 },
    }),
  });
  if (!response.ok) throw new Error(`Ollama ${load ? "load" : "unload"} failed (${response.status})`);
  return { model: profile.model, ok: true };
}
