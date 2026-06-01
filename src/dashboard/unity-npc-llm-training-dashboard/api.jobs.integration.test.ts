import { test } from "node:test";
import * as assert from "node:assert/strict";
import { spawn, type ChildProcessWithoutNullStreams } from "node:child_process";

const DASHBOARD_DIR = "/home/athar/Projects/Unsloth_Core/frontend_control/unity-npc-llm-training-dashboard";

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

const waitForServer = async (baseUrl: string): Promise<void> => {
  const deadline = Date.now() + 20_000;
  while (Date.now() < deadline) {
    try {
      const res = await fetch(`${baseUrl}/api/health`);
      if (res.ok || res.status === 503) return;
    } catch {
      // retry
    }
    await sleep(250);
  }
  throw new Error("Timed out waiting for dashboard server");
};

const startServer = async (port: number) => {
  const child: ChildProcessWithoutNullStreams = spawn(
    "./node_modules/.bin/tsx",
    ["server.ts"],
    {
      cwd: DASHBOARD_DIR,
      env: { ...process.env, PORT: String(port) },
      stdio: ["ignore", "pipe", "pipe"],
      detached: true,
    },
  );

  let bootOutput = "";
  child.stdout.on("data", (chunk) => { bootOutput += chunk.toString(); });
  child.stderr.on("data", (chunk) => { bootOutput += chunk.toString(); });

  const baseUrl = `http://127.0.0.1:${port}`;
  await waitForServer(baseUrl);

  return { child, baseUrl, bootOutputRef: () => bootOutput };
};

const stopServer = async (child: ChildProcessWithoutNullStreams) => {
  try { process.kill(-child.pid!, "SIGTERM"); } catch {}
  await sleep(500);
  try { process.kill(-child.pid!, "SIGKILL"); } catch {}
};

test("/api/jobs reflects stage-derived progress for a newly started command", async () => {
  const { child, baseUrl } = await startServer(3211);
  let startedJobId: string | null = null;

  try {
    const startRes = await fetch(`${baseUrl}/api/commands/start`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        commandId: "dataset-generate",
        type: "Dataset",
        spec: "subjects/nonexistent_integration_spec.json",
      }),
    });

    if (!startRes.ok) {
      const errText = await startRes.text();
      assert.fail(`start command failed: ${startRes.status} ${errText}`);
    }

    const started = (await startRes.json()) as { id: string; status: string; progress: number; commandId: string };
    startedJobId = started.id;

    assert.equal(started.commandId, "dataset-generate");
    assert.equal(started.status, "running");
    assert.equal(started.progress, 10); // 5 stages: Dataset 0.5/5 * 100 = 10

    const jobsRes = await fetch(`${baseUrl}/api/jobs`);
    assert.equal(jobsRes.ok, true, `jobs fetch failed: ${jobsRes.status}`);
    const jobs = (await jobsRes.json()) as Array<{ id: string; progress: number; status: string; commandId?: string }>;

    const live = jobs.find((job) => job.id === started.id);
    assert.ok(live, "started job not found in /api/jobs");
    assert.equal(live?.commandId, "dataset-generate");
    assert.ok(
      typeof live?.progress === "number" && live.progress >= 1 && live.progress <= 99,
      "progress should be stage-derived 1..99 while in-flight",
    );
  } finally {
    if (startedJobId) {
      try {
        await fetch(`${baseUrl}/api/commands/stop`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ id: startedJobId }),
        });
      } catch {
        // best effort
      }
    }
    await stopServer(child);
  }
});

test("/api/jobs/state exposes canonical registry controls and manual resync can re-enable sync", async () => {
  const { child, baseUrl } = await startServer(3213);

  try {
    const bootstrapRes = await fetch(`${baseUrl}/api/jobs/sync`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ force: true }),
    });
    assert.equal(bootstrapRes.ok, true, `bootstrap sync failed: ${bootstrapRes.status} ${await bootstrapRes.text()}`);

    const initialRes = await fetch(`${baseUrl}/api/jobs/state`);
    assert.equal(initialRes.ok, true, `state fetch failed: ${initialRes.status}`);
    const initial = (await initialRes.json()) as { jobs: Array<{ id: string }>; workflowCount: number; autoSyncExternal: boolean };
    assert.equal(Array.isArray(initial.jobs), true);
    assert.equal(initial.workflowCount >= 0, true);
    assert.equal(initial.autoSyncExternal, true);

    const clearRes = await fetch(`${baseUrl}/api/jobs/clear`, { method: "POST" });
    let clearSucceeded = false;
    if (clearRes.status === 409) {
      // External processes may be running (e.g. ./ucore commands) — 409 is correct behavior
      const err = await clearRes.json() as { error: string; running: string[] };
      assert.equal(err.error, "Cannot clear while jobs are running");
      assert.ok(Array.isArray(err.running) && err.running.length > 0);
    } else {
      assert.equal(clearRes.ok, true, `clear failed: ${clearRes.status} ${await clearRes.text()}`);
      clearSucceeded = true;
    }

    if (clearSucceeded) {
      const clearedRes = await fetch(`${baseUrl}/api/jobs/state`);
      assert.equal(clearedRes.ok, true, `cleared state fetch failed: ${clearedRes.status}`);
      const cleared = (await clearedRes.json()) as { jobs: Array<{ id: string }>; workflowCount: number; autoSyncExternal: boolean };
      assert.equal(cleared.jobs.length, 0);
      assert.equal(cleared.workflowCount, 0);
      assert.equal(cleared.autoSyncExternal, false);
    } else {
      // When 409, autoSyncExternal remains true (clear never executed)
      const stateAfter = await fetch(`${baseUrl}/api/jobs/state`);
      assert.equal(stateAfter.ok, true);
      const after = await stateAfter.json() as { autoSyncExternal: boolean; jobs: Array<unknown> };
      assert.equal(after.autoSyncExternal, true);
    }

    const resyncRes = await fetch(`${baseUrl}/api/jobs/sync`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ force: true }),
    });
    assert.equal(resyncRes.ok, true, `resync failed: ${resyncRes.status} ${await resyncRes.text()}`);

    const resyncedRes = await fetch(`${baseUrl}/api/jobs/state`);
    assert.equal(resyncedRes.ok, true, `resynced state fetch failed: ${resyncedRes.status}`);
    const resynced = (await resyncedRes.json()) as { autoSyncExternal: boolean };
    assert.equal(resynced.autoSyncExternal, true);
  } finally {
    await stopServer(child);
  }
});

test("stopping a running job transitions to stopped with stopped stage", async () => {
  const { child, baseUrl } = await startServer(3212);
  let startedJobId: string | null = null;

  try {
    const startRes = await fetch(`${baseUrl}/api/commands/start`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        commandId: "dataset-generate",
        type: "Dataset",
        spec: "subjects/nonexistent_integration_spec_2.json",
      }),
    });

    if (!startRes.ok) {
      const errText = await startRes.text();
      assert.fail(`start command failed: ${startRes.status} ${errText}`);
    }

    const started = (await startRes.json()) as { id: string; status: string };
    startedJobId = started.id;
    assert.equal(started.status, "running");

    const stopRes = await fetch(`${baseUrl}/api/commands/stop`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: startedJobId }),
    });
    assert.equal(stopRes.ok, true, `stop command failed: ${stopRes.status} ${await stopRes.text()}`);

    let stoppedJob: { status: string; stages: Array<{ status: string }> } | undefined;
    const deadline = Date.now() + 10_000;
    while (Date.now() < deadline) {
      const jobsRes = await fetch(`${baseUrl}/api/jobs`);
      assert.equal(jobsRes.ok, true, `jobs fetch failed: ${jobsRes.status}`);
      const jobs = (await jobsRes.json()) as Array<{
        id: string;
        status: string;
        stages: Array<{ status: "completed" | "running" | "pending" | "failed" | "stopped" }>;
      }>;

      const job = jobs.find((j) => j.id === startedJobId);
      if (job?.status === "stopped") {
        stoppedJob = job;
        break;
      }
      await sleep(200);
    }

    assert.ok(stoppedJob, "job did not transition to stopped in time");
    const hasStoppedStage = stoppedJob!.stages.some((stage) => stage.status === "stopped");
    assert.equal(hasStoppedStage, true, "expected at least one stage to be marked stopped");
  } finally {
    await stopServer(child);
  }
});


