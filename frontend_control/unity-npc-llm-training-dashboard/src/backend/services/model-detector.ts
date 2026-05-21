import { execSync } from "child_process";
import path from "path";
import type { LocalModelStatus, LocalModelSource } from "../types";

// ── Helpers ────────────────────────────────────────────────────────────────

function isoNow(): string {
  return new Date().toISOString();
}

function tokenizeProcessArgs(args: string): string[] {
  const matches = args.match(/(?:[^\s"']+|"[^"]*"|'[^']*')+/g);
  if (!matches) return [];
  return matches.map((token) => token.replace(/^["']|["']$/g, ""));
}

function valueAfterProcessFlag(tokens: string[], flagNames: string[]): string | null {
  for (let index = 0; index < tokens.length; index += 1) {
    const token = tokens[index];
    const matchingFlag = flagNames.find(
      (flagName) => token === flagName || token.startsWith(`${flagName}=`),
    );
    if (!matchingFlag) continue;

    if (token.startsWith(`${matchingFlag}=`)) {
      const [, value] = token.split(/=(.*)/s);
      return value || null;
    }

    return tokens[index + 1] || null;
  }
  return null;
}

function inferNpcKeyFromGgufPath(ggufPath: string): string | null {
  const segments = path.normalize(ggufPath).split(path.sep);
  const exportsIndex = segments.lastIndexOf("exports");
  if (exportsIndex >= 0 && segments[exportsIndex + 1]) return segments[exportsIndex + 1];
  return null;
}

function displayNameFromGgufPath(ggufPath: string): string {
  const basename = path.basename(ggufPath);
  return basename.endsWith(".gguf") ? basename.slice(0, -".gguf".length) : basename;
}

function noLocalModel(updatedAt = isoNow()): LocalModelStatus {
  return { loaded: false, source: "none", displayName: null, updatedAt };
}

// ── Detection ──────────────────────────────────────────────────────────────

export function detectLlamaServerModel(updatedAt: string): LocalModelStatus | null {
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
}

export async function fetchOllamaModel(updatedAt: string): Promise<LocalModelStatus | null> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 1000);

  try {
    const response = await fetch("http://127.0.0.1:11434/api/ps", { signal: controller.signal });
    if (!response.ok) return null;

    const payload = (await response.json()) as {
      models?: Array<{ name?: string; model?: string }>;
    };
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
}

export async function detectLocalModel(): Promise<LocalModelStatus> {
  const updatedAt = isoNow();
  const llamaServerModel = detectLlamaServerModel(updatedAt);
  if (llamaServerModel) return llamaServerModel;

  const ollamaModel = await fetchOllamaModel(updatedAt);
  if (ollamaModel) return ollamaModel;

  return noLocalModel(updatedAt);
}

export type { LocalModelStatus, LocalModelSource };
