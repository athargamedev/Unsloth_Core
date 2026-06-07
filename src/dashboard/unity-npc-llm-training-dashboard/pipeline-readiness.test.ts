import { test } from "node:test";
import * as assert from "node:assert/strict";

import { buildReadinessPlanFromRecords } from "./src/backend/routes/pipeline";
import {
  buildPipelineReadinessUrl,
  DEFAULT_PIPELINE_READINESS_TECHNIQUE,
  DEPRECATED_NOTEBOOKLM_TECHNIQUE,
} from "./src/hooks/useReactQuery";

const artifact = (artifact_type: string, stage: string, path: string, technique = DEFAULT_PIPELINE_READINESS_TECHNIQUE) => ({
  ts: new Date().toISOString(),
  npc_key: "history_guide",
  technique,
  stage,
  artifact_type,
  path,
  sha256: `sha-${artifact_type}`,
});

test("default pipeline readiness request uses ollama technique", () => {
  const url = buildPipelineReadinessUrl("history_guide");
  assert.equal(DEFAULT_PIPELINE_READINESS_TECHNIQUE, "ollama");
  assert.match(url, /[?&]technique=ollama(?:&|$)/);
});

test("buildReadinessPlanFromRecords reports missing artifacts and next required stage", () => {
  const plan = buildReadinessPlanFromRecords(
    [
      artifact("dataset_raw", "generate", "subjects/datasets/history_guide/ollama/train.jsonl"),
      artifact("dataset_clean", "sanitize", "subjects/datasets/history_guide/ollama/train_clean.jsonl"),
      artifact("quality_summary", "dataset_eval", "subjects/datasets/history_guide/ollama/quality_summary.json"),
    ],
    "history_guide",
    "evaluate",
    DEFAULT_PIPELINE_READINESS_TECHNIQUE,
    "/repo/.pipeline/artifacts.jsonl",
  );

  assert.equal("error" in plan, false);
  if ("error" in plan) return;
  assert.equal(plan.ready, false);
  assert.equal(plan.next_required_stage, "train");
  assert.equal(plan.artifact_count, 3);
  assert.deepEqual(plan.steps.map((step) => step.stage), [
    "generate",
    "sanitize",
    "dataset_eval",
    "train",
    "export",
    "evaluate",
  ]);
  assert.deepEqual(plan.steps.find((step) => step.stage === "train")?.missing_artifacts, []);
  assert.deepEqual(plan.steps.find((step) => step.stage === "export")?.missing_artifacts, ["adapter_checkpoint"]);
  assert.deepEqual(plan.steps.find((step) => step.stage === "evaluate")?.missing_artifacts, ["gguf_adapter"]);
});

test("buildReadinessPlanFromRecords marks evaluate ready when all canonical artifacts exist", () => {
  const plan = buildReadinessPlanFromRecords(
    [
      artifact("dataset_raw", "generate", "raw.jsonl"),
      artifact("dataset_clean", "sanitize", "clean.jsonl"),
      artifact("quality_summary", "dataset_eval", "quality_summary.json"),
      artifact("adapter_checkpoint", "train", "outputs/history_guide/runs/run-1"),
      artifact("gguf_adapter", "export", "exports/history_guide/history_guide-lora-f16.gguf"),
    ],
    "history_guide",
    "evaluate",
    DEFAULT_PIPELINE_READINESS_TECHNIQUE,
  );

  assert.equal("error" in plan, false);
  if ("error" in plan) return;
  assert.equal(plan.ready, true);
  assert.equal(plan.next_required_stage, "evaluate");
  assert.deepEqual(plan.steps.flatMap((step) => step.missing_artifacts), []);
});

test("buildReadinessPlanFromRecords filters by technique", () => {
  const plan = buildReadinessPlanFromRecords(
    [
      artifact("dataset_raw", "generate", "template/raw.jsonl", "template"),
      artifact("dataset_clean", "sanitize", "template/clean.jsonl", "template"),
    ],
    "history_guide",
    "dataset_eval",
    DEFAULT_PIPELINE_READINESS_TECHNIQUE,
  );

  assert.equal("error" in plan, false);
  if ("error" in plan) return;
  assert.equal(plan.artifact_count, 0);
  assert.equal(plan.ready, false);
  assert.equal(plan.next_required_stage, "generate");
  assert.deepEqual(plan.steps.find((step) => step.stage === "sanitize")?.missing_artifacts, ["dataset_raw"]);
});


test("deprecated notebooklm readiness requires explicit opt-in", () => {
  const url = buildPipelineReadinessUrl("history_guide", DEPRECATED_NOTEBOOKLM_TECHNIQUE);
  assert.equal(DEPRECATED_NOTEBOOKLM_TECHNIQUE, "notebooklm");
  assert.match(url, /[?&]technique=notebooklm(?:&|$)/);
});
