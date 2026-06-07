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

test("dashboard dataset-eval command exposes hosted W&B judge flags", () => {
  const args = command("dataset-eval").build({
    spec: "subjects/NPC_specs/history_guide.json",
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

  assert.deepEqual(args.slice(0, 3), ["./ucore", "dataset-eval", "subjects/NPC_specs/history_guide.json"]);
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
    spec: "subjects/NPC_specs/history_guide.json",
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

test("dashboard target-run defaults to canonical production workflow", () => {
  const args = command("target-run").build({
    npcKey: "chef_assistant",
    options: {},
  });

  assert.deepEqual(args, [
    "./ucore",
    "target",
    "run",
    "--npc-key",
    "chef_assistant",
    "--technique",
    "ollama",
    "--target-stage",
    "evaluate",
    "--profile",
    "npc-production-grounded",
    "--dry-run",
  ]);
});

test("dashboard target-run can run resume without invalid json flag", () => {
  const args = command("target-run").build({
    npcKey: "history_guide",
    options: {
      dryRun: false,
      resume: true,
      targetStage: "dataset_eval",
    },
  });

  assert.deepEqual(args, [
    "./ucore",
    "target",
    "run",
    "--npc-key",
    "history_guide",
    "--technique",
    "ollama",
    "--target-stage",
    "dataset_eval",
    "--profile",
    "npc-production-grounded",
    "--resume",
  ]);
  assert.ok(!args.includes("--json"));
});

test("dashboard pipeline command exposes dataset and eval judge selectors", () => {
  const args = command("pipeline").build({
    spec: "subjects/NPC_specs/history_guide.json",
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
