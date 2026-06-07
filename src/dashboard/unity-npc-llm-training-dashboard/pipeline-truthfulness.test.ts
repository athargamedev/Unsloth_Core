import { test } from "node:test";
import * as assert from "node:assert/strict";

import {
  buildNpcStatusFromReadinessPlan,
  buildReadinessPlanFromRecords,
} from "./src/backend/routes/pipeline";

const artifact = (artifact_type: string, stage: string, artifactPath: string, technique = "ollama") => ({
  ts: new Date().toISOString(),
  npc_key: "chef_assistant",
  technique,
  stage,
  artifact_type,
  path: artifactPath,
  sha256: `sha-${artifact_type}`,
});

test("NPC status is derived from artifact registry readiness, not historical complete events", () => {
  const plan = buildReadinessPlanFromRecords(
    [
      artifact("dataset_raw", "generate", "data/datasets/chef_assistant/ollama/train.jsonl"),
      artifact("dataset_clean", "sanitize", "data/datasets/chef_assistant/ollama/train_clean.jsonl"),
      artifact("quality_summary", "dataset_eval", "data/datasets/chef_assistant/ollama/quality_summary.json"),
      // Deliberately no adapter_checkpoint / gguf_adapter. Historical run events may exist,
      // but dashboard truth must not call export/evaluate ready without artifacts.
    ],
    "chef_assistant",
    "evaluate",
    "ollama",
    "/repo/.pipeline/artifacts.jsonl",
  );
  assert.equal("error" in plan, false);
  if ("error" in plan) return;

  const status = buildNpcStatusFromReadinessPlan(plan);

  assert.equal(status.source, "artifact_registry");
  assert.equal(status.pipeline_health, "blocked");
  assert.equal(status.next_required_stage, "train");
  assert.equal(status.stages.train.ready, true, "train inputs are ready");
  assert.equal(status.stages.export.ready, false, "export is blocked by missing adapter_checkpoint");
  assert.deepEqual(status.stages.export.missing_artifacts, ["adapter_checkpoint"]);
  assert.equal(status.stages.evaluate.ready, false, "evaluate is blocked by missing gguf_adapter");
});

test("NPC status marks evaluate healthy only when readiness plan has all prerequisites", () => {
  const plan = buildReadinessPlanFromRecords(
    [
      artifact("dataset_raw", "generate", "raw.jsonl"),
      artifact("dataset_clean", "sanitize", "clean.jsonl"),
      artifact("quality_summary", "dataset_eval", "quality_summary.json"),
      artifact("adapter_checkpoint", "train", "outputs/chef_assistant/runs/run-1"),
      artifact("gguf_adapter", "export", "exports/chef_assistant/chef_assistant-lora-f16.gguf"),
      artifact("eval_index", "evaluate", "eval/reports/chef_assistant/index.json"),
    ],
    "chef_assistant",
    "evaluate",
    "ollama",
  );
  assert.equal("error" in plan, false);
  if ("error" in plan) return;

  const status = buildNpcStatusFromReadinessPlan(plan);

  assert.equal(status.pipeline_health, "healthy");
  assert.equal(status.ready, true);
  assert.equal(status.next_required_stage, "evaluate");
  assert.equal(status.stages.evaluate.has_output, true);
});
