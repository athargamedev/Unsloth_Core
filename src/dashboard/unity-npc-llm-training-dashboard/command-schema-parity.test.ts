import { test } from "node:test";
import * as assert from "node:assert/strict";
import path from "node:path";

import { buildCommandDefinitions } from "./src/backend/services/command-builder";
import {
  buildAvailableCommandPayloads,
  buildCommandSchemaPayload,
} from "./src/backend/routes/commands";

const repoRoot = path.resolve(process.cwd(), "../../..");
const commandMap = new Map(buildCommandDefinitions(repoRoot).map((cmd) => [cmd.id, cmd]));

test("available command payload includes P5/P6 canonical CLI surfaces", () => {
  const payload = buildAvailableCommandPayloads(commandMap);
  const ids = payload.map((cmd) => cmd.id).sort();

  assert.ok(ids.includes("target-plan"), "target plan should be a dashboard command");
  assert.ok(ids.includes("target-run"), "target run should be a dashboard command");
  assert.ok(ids.includes("compare-canonical-runs"), "canonical comparison should be a dashboard command");
  assert.ok(ids.includes("promote"), "promotion dry-run should be a dashboard command");

  const promote = payload.find((cmd) => cmd.id === "promote");
  assert.equal(promote?.cli?.command, "promote");
  assert.equal(promote?.cli?.source, "ucore");
});

test("command schema payload exposes typed defaults/enums and resolved npcKey templates", () => {
  const schemas = buildCommandSchemaPayload(commandMap, "chef_assistant");

  assert.equal(schemas["target-run"].cli.command, "target");
  assert.equal(schemas["target-run"].cli.subcommand, "run");
  assert.equal(schemas["target-run"].fields["options.dryRun"].type, "boolean");
  assert.deepEqual(schemas["target-run"].fields["options.targetStage"].enum, [
    "generate",
    "sanitize",
    "dataset_eval",
    "train",
    "export",
    "evaluate",
  ]);
  assert.equal(schemas["target-run"].fields["options.profile"].default, "npc-production-grounded");

  assert.equal(schemas["promote"].fields["options.dryRun"].default, true);
  assert.equal(schemas["promote"].fields["options.candidateRunId"].required, true);
  assert.equal(schemas["dataset-generate"].fields.spec.default, "data/npcs/specs/chef_assistant.json");
  assert.equal(schemas["dataset-generate"].fields["options.technique"].default, "ollama");
  assert.deepEqual(schemas["dataset-generate"].fields.spec.roots?.slice(0, 2), ["data", "subjects"]);
});
