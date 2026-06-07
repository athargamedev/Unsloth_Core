import { test } from "node:test";
import * as assert from "node:assert/strict";
import path from "node:path";

import { buildCommandDefinitions } from "./src/backend/services/command-builder";

const repoRoot = path.resolve(process.cwd(), "../../..");
const command = (id: string) => {
  const found = buildCommandDefinitions(repoRoot).find((definition) => definition.id === id);
  assert.ok(found, `command ${id} not found`);
  return found;
};


test("dashboard dataset-generate defaults to canonical Ollama command and spec path", () => {
  const definition = command("dataset-generate");
  assert.equal(definition.schema.spec.default, "data/npcs/specs/{npcKey}.json");
  assert.equal(definition.schema["options.technique"].default, "ollama");
  assert.deepEqual(definition.schema.spec.roots?.slice(0, 2), ["data", "subjects"]);

  const args = definition.build({
    spec: "data/npcs/specs/history_guide.json",
    options: { technique: "ollama", model: "qwen2.5:7b" },
  });

  assert.deepEqual(args, ["./ucore", "generate-ollama", "data/npcs/specs/history_guide.json", "--model", "qwen2.5:7b"]);
});

test("dashboard dataset-generate preserves explicit template smoke command", () => {
  const args = command("dataset-generate").build({
    spec: "data/npcs/specs/history_guide.json",
    options: { technique: "template" },
  });

  assert.deepEqual(args, ["./ucore", "generate", "data/npcs/specs/history_guide.json", "--technique", "template"]);
});

test("dashboard dataset-eval command exposes hosted W&B judge flags", () => {
  const args = command("dataset-eval").build({
    spec: "data/npcs/specs/history_guide.json",
    options: {
      technique: "ollama",
      judgeProvider: "wandb",
      judgeModel: "meta-llama/Llama-3.1-8B-Instruct",
      wandb: true,
      wandbProject: "unsloth-core",
      wandbEntity: "andreabenathar-twl-games",
      wandbInferenceProject: "judge-project",
      wandbInferenceEntity: "judge-team",
    },
  });

  assert.deepEqual(args.slice(0, 3), ["./ucore", "dataset-eval", "data/npcs/specs/history_guide.json"]);
  assert.ok(args.includes("--judge-provider"));
  assert.ok(args.includes("wandb"));
  assert.ok(args.includes("--judge-model"));
  assert.ok(args.includes("meta-llama/Llama-3.1-8B-Instruct"));
  assert.ok(args.includes("--wandb"));
  assert.ok(args.includes("--wandb-inference-project"));
  assert.ok(args.includes("judge-project"));
  assert.ok(args.includes("--wandb-inference-entity"));
  assert.ok(args.includes("judge-team"));
});

test("dashboard evaluate command exposes hosted W&B judge flags", () => {
  const args = command("evaluate").build({
    spec: "data/npcs/specs/history_guide.json",
    options: {
      baseline: ".models/base.gguf",
      candidate: "exports/history_guide/unity/history_guide-lora-f16.gguf",
      judge: true,
      judgeProvider: "wandb",
      judgeModel: "meta-llama/Llama-3.1-8B-Instruct",
      wandbInferenceProject: "judge-project",
      wandbInferenceEntity: "judge-team",
    },
  });

  assert.ok(args.includes("--judge"));
  assert.ok(args.includes("--judge-provider"));
  assert.ok(args.includes("wandb"));
  assert.ok(args.includes("--wandb-inference-project"));
  assert.ok(args.includes("judge-project"));
});

test("dashboard feedback command exposes hosted W&B DeepEval judge flags", () => {
  const args = command("feedback").build({
    options: {
      feedbackJson: "eval/results/feedback/history_guide.json",
      deepevalJudgeProvider: "wandb",
      deepevalJudgeModel: "meta-llama/Llama-3.1-8B-Instruct",
      wandbInferenceProject: "judge-project",
      wandbInferenceEntity: "judge-team",
    },
  });

  assert.deepEqual(args.slice(0, 2), ["./ucore", "feedback"]);
  assert.ok(args.includes("--deepeval-judge-provider"));
  assert.ok(args.includes("wandb"));
  assert.ok(args.includes("--wandb-inference-project"));
  assert.ok(args.includes("judge-project"));
});

test("dashboard pipeline command exposes dataset and eval judge selectors", () => {
  const args = command("pipeline").build({
    spec: "data/npcs/specs/history_guide.json",
    preset: "safe-any",
    options: {
      technique: "ollama",
      datasetEvalJudgeProvider: "wandb",
      datasetEvalJudgeModel: "meta-llama/Llama-3.1-8B-Instruct",
      evalJudge: true,
      evalJudgeProvider: "wandb",
      evalJudgeModel: "meta-llama/Llama-3.1-8B-Instruct",
      wandbInferenceProject: "judge-project",
      wandbInferenceEntity: "judge-team",
    },
  });

  assert.ok(args.includes("--dataset-eval-judge-provider"));
  assert.ok(args.includes("--dataset-eval-judge-model"));
  assert.ok(args.includes("--eval-judge"));
  assert.ok(args.includes("--eval-judge-provider"));
  assert.ok(args.includes("--wandb-inference-project"));
});
