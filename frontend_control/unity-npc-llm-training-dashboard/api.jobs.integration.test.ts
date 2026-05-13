import test from "node:test";
import assert from "node:assert/strict";
import { spawn, type ChildProcessWithoutNullStreams } from "node:child_process";
import path from "node:path";

const DASHBOARD_DIR = "/home/athar/Projects/Unsloth_Core/frontend_control/unity-npc-llm-training-dashboard";
const PORT = 3211;
const BASE_URL = `http://127.0.0.1:${PORT}`;

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

const waitForServer = async (): Promise<void> => {
  const deadline = Date.now() + 20_000;
  while (Date.now() < deadline) {
    try {
      const res = await fetch(`${BASE_URL}/api/health`);
      if (res.ok || res.status === 503) return;
    } catch {
      // retry
    }
    await sleep(250);
  }
  throw new Error("Timed out waiting for dashboard server");
};

test("/api/jobs reflects stage-derived progress for a newly started command", async () => {
  const child: ChildProcessWithoutNullStreams = spawn(
    "npx",
    ["tsx", "server.ts"],
    {
      cwd: DASHBOARD_DIR,
      env: { ...process.env, PORT: String(PORT) },
      stdio: ["ignore", "pipe", "pipe"],
    },
  );

  let bootOutput = "";
  child.stdout.on("data", (chunk) => { bootOutput += chunk.toString(); });
  child.stderr.on("data", (chunk) => { bootOutput += chunk.toString(); });

  try {
    await waitForServer();

    const startRes = await fetch(`${BASE_URL}/api/commands/start`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        commandId: "dataset-generate",
        type: "Dataset",
        spec: "subjects/nonexistent_integration_spec.json",
      }),
    });

    assert.equal(startRes.ok, true, `start command failed: ${startRes.status} ${await startRes.text()}`);
    const started = (await startRes.json()) as { id: string; status: string; progress: number; commandId: string };

    // dataset stage should be running and progress should be midpoint of stage 0 across 4 stages => 13
    assert.equal(started.commandId, "dataset-generate");
    assert.equal(started.status, "running");
    assert.equal(started.progress, 13);

    const jobsRes = await fetch(`${BASE_URL}/api/jobs`);
    assert.equal(jobsRes.ok, true, `jobs fetch failed: ${jobsRes.status}`);
    const jobs = (await jobsRes.json()) as Array<{ id: string; progress: number; status: string; commandId?: string }>;

    const live = jobs.find((job) => job.id === started.id);
    assert.ok(live, "started job not found in /api/jobs");
    assert.equal(live?.commandId, "dataset-generate");
    assert.ok(typeof live?.progress === "number" && live.progress >= 1 && live.progress <= 99, "progress should be stage-derived 1..99 while in-flight");
  } finally {
    try { process.kill(child.pid!, "SIGTERM"); } catch {}
    await sleep(500);
    try { process.kill(child.pid!, "SIGKILL"); } catch {}
  }
});
