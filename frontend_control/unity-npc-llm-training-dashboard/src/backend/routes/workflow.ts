import type { Express, Request, Response } from "express";
import path from "path";
import fs from "fs";
import { spawn } from "child_process";
import type { RouterDependencies, Workflow, WorkflowStep, Job, StartCommandPayload } from "../types";
import { updateStagesFromTruth, parseLoss, makeId, isoNow, runningProcesses, terminalJobState, stopEscalationTimers } from "../services/job-runner";

const MAX_LOG_LINES = 2000;

/**
 * Registers /api/workflow/* endpoints.
 */
export function registerRoutes(app: Express, deps: RouterDependencies): void {
  const {
    registry,
    commandMap,
    repoRoot,
    broadcast,
    globalLog,
    persistRegistry,
    flushPersist,
    invalidateJobsCache,
    unloadGemmaModel,
  } = deps;

  // ── GET /api/workflows ──────────────────────────────────────────────────
  app.get("/api/workflows", (_req: Request, res: Response) => {
    res.json(registry.workflows);
  });

  // ── POST /api/workflow/start ────────────────────────────────────────────
  app.post("/api/workflow/start", (req: Request, res: Response) => {
    try {
      const spec = String(req.body?.spec || "").trim();
      const preset = String(req.body?.preset || "").trim();
      const npcKey = spec.replace(/^subjects\//, "").replace(/\.json$/, "");
      const technique = String(
        req.body?.technique || (npcKey === "workflow_assistant" ? "docs" : "template"),
      ).trim();

      if (!spec) {
        res.status(400).json({ error: "spec is required" });
        return;
      }

      const isWorkflowTool = npcKey === "workflow_assistant";
      const workflowId = `wf_${Date.now()}`;

      // Resolve model ID for export step
      let exportModelId = String(req.body?.options?.baseModel || "");
      if (!exportModelId) {
        try {
          const specPath = path.join(repoRoot, "subjects", `${npcKey}.json`);
          if (fs.existsSync(specPath)) {
            const specData = JSON.parse(
              fs.readFileSync(specPath, "utf8"),
            ) as Record<string, unknown>;
            exportModelId = String(
              specData.model ||
                specData.model_id ||
                ((specData.llm as Record<string, unknown>) || {}).model_name ||
                "",
            );
          }
        } catch {
          // ignore
        }
      }

      const steps: WorkflowStep[] = [
        {
          commandId: "dataset-generate",
          status: "pending",
          payload: {
            commandId: "dataset-generate",
            type: "Dataset",
            spec,
            options: { technique },
          },
        },
        {
          commandId: "dataset-sanitize",
          status: "pending",
          payload: {
            commandId: "dataset-sanitize",
            type: "Dataset",
            spec,
            options: {
              datasetPath: `subjects/datasets/${npcKey}/${technique}/train.jsonl`,
            },
          },
        },
      ];

      if (isWorkflowTool) {
        steps.push({
          commandId: "validate-config",
          status: "pending",
          payload: {
            commandId: "validate-config",
            type: "Validation",
            spec,
            preset,
            options: {
              dataPath: `subjects/datasets/${npcKey}/${technique}/train_clean.jsonl`,
              requireCanonical: true,
            },
          },
        });
      } else {
        steps.push({
          commandId: "train",
          status: "pending",
          payload: {
            commandId: "train",
            type: "Training",
            spec,
            preset,
            npcKey,
            options: { ...(req.body?.options || {}), technique },
          },
        });
      }

      if (!isWorkflowTool && exportModelId) {
        steps.push({
          commandId: "export",
          status: "pending",
          payload: {
            commandId: "export",
            type: "Export",
            npcKey,
            options: { modelId: exportModelId },
          },
        });
      }

      const workflow: Workflow = {
        id: workflowId,
        name: `Pipeline: ${npcKey} (${preset || "default"})`,
        spec,
        steps,
        currentStep: 0,
        overallStatus: "running",
        createdAt: isoNow(),
      };

      registry.workflows.unshift(workflow);
      flushPersist(registry);

      // Start the first step
      const firstStep = steps[0];
      const firstDef = commandMap.get(firstStep.commandId);
      if (!firstDef) {
        res.status(500).json({ error: `Unknown command: ${firstStep.commandId}` });
        return;
      }

      const command = firstDef.build(firstStep.payload as StartCommandPayload);
      const chainNext = steps.length > 1
        ? { commandId: steps[1].commandId, payload: steps[1].payload }
        : undefined;

      const job: Job = {
        id: makeId(),
        name: `${firstDef.label} (${npcKey})`,
        type: firstDef.type,
        commandId: firstDef.id,
        npcKey,
        workflowId,
        chainNext,
        status: "running",
        progress: 5,
        loss: null,
        createdAt: isoNow(),
        startedAt: isoNow(),
        command,
        stages: [
          { name: "Dataset Prep", status: "pending", logs: [] },
          { name: "Training", status: "pending", logs: [] },
          { name: "Evaluation", status: "pending", logs: [] },
          { name: "Export", status: "pending", logs: [] },
          { name: "Feedback", status: "pending", logs: [] },
        ],
        logs: [],
      };

      updateStagesFromTruth(job);

      firstStep.status = "running";
      firstStep.jobId = job.id;
      registry.jobs.unshift(job);
      globalLog(
        registry,
        `[WORKFLOW] starting ${workflowId} step 1/${steps.length}: ${command.join(" ")}`,
      );
      persistRegistry(registry);
      broadcast("job_update", {
        id: job.id,
        status: job.status,
        loss: job.loss,
        progress: job.progress,
      });

      unloadGemmaModel();
      const child = spawn(command[0], command.slice(1), {
        cwd: repoRoot,
        shell: false,
        detached: true,
        env: {
          ...process.env,
          WORKFLOW_HOOKS_PATH: process.env.WORKFLOW_HOOKS_PATH || "",
        },
      });
      runningProcesses.set(job.id, child);
      terminalJobState.set(job.id, {
        stopRequested: false,
        terminal: false,
      });

      // Process output
      const consume =
        (jobRef: Job, stepRef: WorkflowStep, _stepIndex: number) =>
        (chunk: Buffer, source: "stdout" | "stderr") => {
          const lines = chunk
            .toString()
            .split("\n")
            .map((l) => l.trim())
            .filter(Boolean);
          for (const line of lines) {
            const prefixed = `[${source.toUpperCase()}][${jobRef.id}] ${line}`;
            jobRef.logs.push(prefixed);
            jobRef.logs = jobRef.logs.slice(-MAX_LOG_LINES);

            const parsedLossValue = parseLoss(line);
            if (parsedLossValue !== null) {
              jobRef.loss = parsedLossValue;
              broadcast("job_update", {
                id: jobRef.id,
                status: jobRef.status,
                loss: jobRef.loss,
                progress: jobRef.progress,
              });
            }
            updateStagesFromTruth(jobRef);
          }
          persistRegistry(registry);
        };

      const jobConsume = consume(job, firstStep, 0);
      child.stdout.on("data", (chunk: Buffer) => jobConsume(chunk, "stdout"));
      child.stderr.on("data", (chunk: Buffer) => jobConsume(chunk, "stderr"));

      child.on("close", (code: number | null) => {
        const terminalState = terminalJobState.get(job.id);
        const escalationTimer = stopEscalationTimers.get(job.id);
        if (escalationTimer) {
          clearTimeout(escalationTimer);
          stopEscalationTimers.delete(job.id);
        }
        runningProcesses.delete(job.id);
        terminalJobState.delete(job.id);
        if (terminalState?.terminal) return;

        job.exitCode = code ?? -1;
        job.finishedAt = isoNow();
        if (terminalState?.stopRequested || job.stopRequested) {
          job.status = "stopped";
          job.terminalReason = "user_requested_stop";
        } else {
          job.status = code === 0 ? "completed" : "failed";
        }

        firstStep.status = code === 0 ? "completed" : "failed";
        workflow.currentStep = 1;

        if (code !== 0) {
          workflow.overallStatus = "failed";
          workflow.finishedAt = isoNow();
        }

        updateStagesFromTruth(job);
        globalLog(registry, `[SYSTEM] ${job.id} ${job.status} (exit ${code})`);
        flushPersist(registry);
        invalidateJobsCache();
        broadcast("job_update", {
          id: job.id,
          status: job.status,
          loss: job.loss,
          progress: job.progress,
        });

        // Chain to next step
        if (code === 0 && chainNext && steps.length > 1) {
          chainToNextStep(steps, 1, workflow, npcKey, commandMap, deps);
        }
      });

      res.json({ workflow, job });
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Failed to start workflow";
      res.status(400).json({ error: message });
    }
  });
}

function chainToNextStep(
  steps: WorkflowStep[],
  stepIndex: number,
  workflow: Workflow,
  npcKey: string,
  commandMap: Map<string, { id: string; label: string; type: string; build: (payload: StartCommandPayload) => string[]; requiredFields: string[] }>,
  deps: RouterDependencies,
) {
  const step = steps[stepIndex];
  if (!step) {
    // No more steps — workflow is done
    workflow.overallStatus = "completed";
    workflow.finishedAt = isoNow();
    deps.flushPersist(deps.registry);
    return;
  }

  const {
    registry,
    repoRoot,
    broadcast,
    globalLog,
    persistRegistry,
    flushPersist,
    invalidateJobsCache,
    unloadGemmaModel,
  } = deps;

  const commandDef = commandMap.get(step.commandId);
  if (!commandDef) {
    globalLog(registry, `[WORKFLOW] unknown command ${step.commandId} — aborting workflow ${workflow.id}`);
    step.status = "failed";
    workflow.overallStatus = "failed";
    workflow.finishedAt = isoNow();
    flushPersist(registry);
    return;
  }

  // Determine the next step after this one for chainNext
  const nextStepIndex = stepIndex + 1;
  const nextStep = steps[nextStepIndex];
  const chainNext = nextStep
    ? { commandId: nextStep.commandId, payload: nextStep.payload }
    : undefined;

  // Build the command string array
  const command = commandDef.build(step.payload as StartCommandPayload);

  // Create the Job for this step
  const job: Job = {
    id: makeId(),
    name: `${commandDef.label} (${npcKey})`,
    type: commandDef.type,
    commandId: commandDef.id,
    npcKey,
    workflowId: workflow.id,
    chainNext,
    status: "running",
    progress: 5,
    loss: null,
    createdAt: isoNow(),
    startedAt: isoNow(),
    command,
    stages: [
      { name: "Dataset Prep", status: "pending", logs: [] },
      { name: "Training", status: "pending", logs: [] },
      { name: "Evaluation", status: "pending", logs: [] },
      { name: "Export", status: "pending", logs: [] },
      { name: "Feedback", status: "pending", logs: [] },
    ],
    logs: [],
  };

  updateStagesFromTruth(job);

  // Update the workflow and step state
  step.status = "running";
  step.jobId = job.id;
  workflow.currentStep = stepIndex;

  registry.jobs.unshift(job);
  globalLog(
    registry,
    `[WORKFLOW] chaining ${workflow.id} step ${stepIndex + 1}/${steps.length}: ${command.join(" ")}`,
  );
  persistRegistry(registry);
  broadcast("job_update", {
    id: job.id,
    status: job.status,
    loss: job.loss,
    progress: job.progress,
  });

  // Spawn the child process
  unloadGemmaModel();
  const child = spawn(command[0], command.slice(1), {
    cwd: repoRoot,
    shell: false,
    detached: true,
    env: {
      ...process.env,
      WORKFLOW_HOOKS_PATH: process.env.WORKFLOW_HOOKS_PATH || "",
    },
  });
  runningProcesses.set(job.id, child);
  terminalJobState.set(job.id, {
    stopRequested: false,
    terminal: false,
  });

  // Process output handler
  const consume =
    (jobRef: Job, stepRef: WorkflowStep, _stepIndex: number) =>
    (chunk: Buffer, source: "stdout" | "stderr") => {
      const lines = chunk
        .toString()
        .split("\n")
        .map((l) => l.trim())
        .filter(Boolean);
      for (const line of lines) {
        const prefixed = `[${source.toUpperCase()}][${jobRef.id}] ${line}`;
        jobRef.logs.push(prefixed);
        jobRef.logs = jobRef.logs.slice(-MAX_LOG_LINES);

        const parsedLossValue = parseLoss(line);
        if (parsedLossValue !== null) {
          jobRef.loss = parsedLossValue;
          broadcast("job_update", {
            id: jobRef.id,
            status: jobRef.status,
            loss: jobRef.loss,
            progress: jobRef.progress,
          });
        }
        updateStagesFromTruth(jobRef);
      }
      persistRegistry(registry);
    };

  const jobConsume = consume(job, step, stepIndex);
  child.stdout.on("data", (chunk: Buffer) => jobConsume(chunk, "stdout"));
  child.stderr.on("data", (chunk: Buffer) => jobConsume(chunk, "stderr"));

  // Close handler — finalize this step and chain to the next
  child.on("close", (code: number | null) => {
    const terminalState = terminalJobState.get(job.id);
    const escalationTimer = stopEscalationTimers.get(job.id);
    if (escalationTimer) {
      clearTimeout(escalationTimer);
      stopEscalationTimers.delete(job.id);
    }
    runningProcesses.delete(job.id);
    terminalJobState.delete(job.id);
    if (terminalState?.terminal) return;

    job.exitCode = code ?? -1;
    job.finishedAt = isoNow();
    if (terminalState?.stopRequested || job.stopRequested) {
      job.status = "stopped";
      job.terminalReason = "user_requested_stop";
    } else {
      job.status = code === 0 ? "completed" : "failed";
    }

    step.status = code === 0 ? "completed" : "failed";

    if (code !== 0) {
      workflow.overallStatus = "failed";
      workflow.finishedAt = isoNow();
    }

    updateStagesFromTruth(job);
    globalLog(registry, `[SYSTEM] ${job.id} ${job.status} (exit ${code})`);
    flushPersist(registry);
    invalidateJobsCache();
    broadcast("job_update", {
      id: job.id,
      status: job.status,
      loss: job.loss,
      progress: job.progress,
    });

    // Chain to the next step on success
    if (code === 0) {
      chainToNextStep(steps, nextStepIndex, workflow, npcKey, commandMap, deps);
    }
  });
}
