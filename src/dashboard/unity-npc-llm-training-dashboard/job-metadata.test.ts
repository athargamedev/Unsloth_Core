import { test } from "node:test";
import * as assert from "node:assert/strict";

import { deriveJobMetadataFromCommand } from "./src/backend/services/job-metadata";

test("deriveJobMetadataFromCommand extracts preset and ollama unload target", () => {
  const derived = deriveJobMetadataFromCommand([
    "./ucore",
    "generate-ollama",
    "data/npcs/specs/history_guide.json",
    "--model",
    "llama3.1-3060-rag:latest",
    "--url",
    "localhost:11434",
    "--preset",
    "fast-3b",
  ]);

  assert.equal(derived.resolvedPreset, "fast-3b");
  assert.deepEqual(derived.ollamaUnloadTarget, {
    model: "llama3.1-3060-rag:latest",
    url: "http://localhost:11434",
  });
});

test("deriveJobMetadataFromCommand ignores non-Ollama base-model paths", () => {
  const derived = deriveJobMetadataFromCommand([
    "./ucore",
    "train",
    "data/npcs/specs/history_guide.json",
    "--from-spec",
    "--preset",
    "safe-any",
    "--base-model",
    "/home/athar/Setup Guide In-Editor Tutorial/Assets/StreamingAssets/Models/llama-3.2-3b-instruct-q4_k_m.gguf",
  ]);

  assert.equal(derived.resolvedPreset, "safe-any");
  assert.equal(derived.ollamaUnloadTarget, null);
});

test("deriveJobMetadataFromCommand supports judge model flags and default ollama url", () => {
  const derived = deriveJobMetadataFromCommand([
    "./ucore",
    "evaluate",
    "data/npcs/specs/astronomy_guide.json",
    "--judge-model",
    "qwen3:latest",
  ]);

  assert.equal(derived.resolvedPreset, null);
  assert.deepEqual(derived.ollamaUnloadTarget, {
    model: "qwen3:latest",
    url: "http://localhost:11434",
  });
});
