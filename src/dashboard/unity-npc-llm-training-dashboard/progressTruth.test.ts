import test from "node:test";
import assert from "node:assert/strict";
import { computeProgressFromStages, deriveStageStatuses, type StageState } from "./progressTruth";

const baseStages = (): StageState[] => [
  { name: "Dataset Prep", status: "pending", logs: [] },
  { name: "Training", status: "pending", logs: [] },
  { name: "Evaluation", status: "pending", logs: [] },
  { name: "Export", status: "pending", logs: [] },
];

test("deriveStageStatuses marks non-pipeline completed job up to active stage", () => {
  const stages = deriveStageStatuses(baseStages(), "completed", 1, false);
  assert.deepEqual(stages.map((s) => s.status), ["completed", "completed", "pending", "pending"]);
});

test("deriveStageStatuses marks pipeline completed job all completed", () => {
  const stages = deriveStageStatuses(baseStages(), "completed", 1, true);
  assert.deepEqual(stages.map((s) => s.status), ["completed", "completed", "completed", "completed"]);
});

test("deriveStageStatuses marks failed active stage correctly", () => {
  const stages = deriveStageStatuses(baseStages(), "failed", 2, false);
  assert.deepEqual(stages.map((s) => s.status), ["completed", "completed", "failed", "pending"]);
});

test("computeProgressFromStages returns stage-midpoint for running", () => {
  const stages = baseStages();
  stages[1].status = "running";
  stages[0].status = "completed";
  const progress = computeProgressFromStages("running", stages);
  assert.equal(progress, 38);
});

test("computeProgressFromStages returns stage-midpoint for stopped", () => {
  const stages = baseStages();
  stages[0].status = "completed";
  stages[1].status = "completed";
  stages[2].status = "stopped";
  const progress = computeProgressFromStages("stopped", stages);
  assert.equal(progress, 63);
});

test("computeProgressFromStages returns 100 for completed", () => {
  const progress = computeProgressFromStages("completed", baseStages());
  assert.equal(progress, 100);
});

test("computeProgressFromStages returns 0 for pending with no active stages", () => {
  const progress = computeProgressFromStages("pending", baseStages());
  assert.equal(progress, 0);
});
