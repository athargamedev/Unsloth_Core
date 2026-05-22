import type { Job } from "../types";

export interface JobOllamaUnloadTarget {
  model: string;
  url: string;
}

export interface DerivedJobMetadata {
  resolvedPreset: string | null;
  ollamaUnloadTarget: JobOllamaUnloadTarget | null;
}

const DEFAULT_OLLAMA_URL = "http://localhost:11434";

function tokenizeCommand(command: string[]): string[] {
  const matches = command
    .join(" ")
    .match(/(?:[^\s"']+|"[^"]*"|'[^']*')+/g);
  if (!matches) return [];
  return matches.map((token) => token.replace(/^["']|["']$/g, ""));
}

function valueAfterFlag(tokens: string[], flagNames: string[]): string | null {
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

    const nextToken = tokens[index + 1];
    return nextToken || null;
  }
  return null;
}

function normalizeOllamaUrl(url: string | null): string {
  if (!url) return DEFAULT_OLLAMA_URL;
  if (/^https?:\/\//i.test(url)) return url;
  return `http://${url}`;
}

function isLikelyOllamaModel(model: string): boolean {
  if (!model) return false;
  if (model.includes("/") || model.endsWith(".gguf")) return false;
  return model.includes(":") || /^[a-z0-9_.-]+$/i.test(model);
}

export function deriveJobMetadataFromCommand(command: string[] | undefined): DerivedJobMetadata {
  if (!command || command.length === 0) {
    return { resolvedPreset: null, ollamaUnloadTarget: null };
  }

  const tokens = tokenizeCommand(command);
  const resolvedPreset = valueAfterFlag(tokens, ["--preset"]);
  const unloadModel = valueAfterFlag(tokens, ["--model", "--judge-model"]);
  const unloadUrl = normalizeOllamaUrl(
    valueAfterFlag(tokens, ["--url", "--base-url", "--ollama-base-url", "--host"]),
  );

  return {
    resolvedPreset,
    ollamaUnloadTarget: unloadModel && isLikelyOllamaModel(unloadModel)
      ? { model: unloadModel, url: unloadUrl }
      : null,
  };
}

export function normalizeJobMetadata(job: Job): Job {
  const derived = deriveJobMetadataFromCommand(job.command);
  job.resolvedPreset = derived.resolvedPreset;
  job.ollamaUnloadTarget = derived.ollamaUnloadTarget;
  return job;
}
