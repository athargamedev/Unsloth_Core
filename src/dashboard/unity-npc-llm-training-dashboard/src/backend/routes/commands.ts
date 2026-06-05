import type { Express, Request, Response } from "express";
import type { RouterDependencies, StartCommandPayload, Job, CommandFieldSchema, CommandDefinition } from "../types";
import { launchJob, stopJob, updateStagesFromTruth, makeId, isoNow } from "../services/job-runner";
import { validateRequiredFields } from "../lib/validation";
import { validate, startCommandSchema, stopJobSchema } from "../middleware/validation";

/**
 * Registers /api/commands/* endpoints.
 *
 * GET  /api/available-commands  — list command definitions (without `build`)
 * GET  /api/command-schemas     — schemas with {npcKey} resolved defaults
 * POST /api/commands/start      — start a command as a new job
 * POST /api/commands/stop       — stop a running job by id
 */
export function registerRoutes(app: Express, deps: RouterDependencies): void {
  const {
    registry,
    commandMap,
    runningProcesses,
    terminalJobState,
    stopEscalationTimers,
    broadcast,
    globalLog,
    persistRegistry,
    flushPersist,
    invalidateJobsCache,
    repoRoot,
    unloadGemmaModel,
  } = deps;

  // ── GET /api/available-commands ─────────────────────────────────────────
  app.get("/api/available-commands", (_req: Request, res: Response) => {
    res.json(buildAvailableCommandPayloads(commandMap));
  });

  // ── GET /api/command-schemas ────────────────────────────────────────────
  app.get("/api/command-schemas", (req: Request, res: Response) => {
    const npcKey =
      String(req.query.npcKey || "history_guide").trim() ||
      "history_guide";

    res.json(buildCommandSchemaPayload(commandMap, npcKey));
  });

  // ── POST /api/commands/start ────────────────────────────────────────────
  app.post("/api/commands/start", validate(startCommandSchema), (req: Request, res: Response) => {
    try {
      const payload = req.body as StartCommandPayload;
      const commandDef = commandMap.get(payload.commandId || "");
      if (!commandDef) {
        res.status(400).json({ error: "Unknown commandId." });
        return;
      }
      if (registry.executionMode === "remote") {
        res.status(501).json({
          error: "Remote runner not implemented yet.",
          mode: "remote",
        });
        return;
      }

      validateRequiredFields(payload, commandDef.requiredFields);

      const command = commandDef.build(payload);
      const job: Job = {
        id: makeId(),
        name: `${commandDef.label}${payload.npcKey ? ` (${payload.npcKey})` : ""}`,
        type: payload.type || commandDef.type,
        commandId: commandDef.id,
        npcKey: payload.npcKey,
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

      const startedJob = launchJob(job, {
        registry,
        repoRoot,
        broadcast,
        globalLog,
        persistRegistry,
        flushPersist,
        invalidateJobsCache,
        unloadGemmaModel,
        isoNow,
        makeId,
        defaultStages: () => [
          { name: "Dataset Prep", status: "pending" as const, logs: [] },
          { name: "Training", status: "pending" as const, logs: [] },
          { name: "Evaluation", status: "pending" as const, logs: [] },
          { name: "Export", status: "pending" as const, logs: [] },
          { name: "Feedback", status: "pending" as const, logs: [] },
        ],
        writeJobLog: (_jobId: string, _line: string) => {
          /* stub — replaced by full impl */
        },
      });
      res.json(startedJob);
    } catch (error) {
      const message =
        error instanceof Error
          ? error.message
          : "Failed to start command.";
      res.status(400).json({ error: message });
    }
  });

  // ── POST /api/commands/stop ─────────────────────────────────────────────
  app.post("/api/commands/stop", validate(stopJobSchema), (req: Request, res: Response) => {
    const { id } = req.body as { id: string };
    const proc = runningProcesses.get(id);
    const job = registry.jobs.find((item) => item.id === id);
    if (!job) {
      res.status(404).json({ error: "Job not found" });
      return;
    }
    if (!proc) {
      res.status(409).json({ error: "Job is not running" });
      return;
    }

    const stopped = stopJob(id);

    if (stopped) {
      job.stopRequested = true;
      globalLog(
        registry,
        `[SYSTEM] stop requested ${id}`,
      );
      flushPersist(registry);
      invalidateJobsCache();
      res.json({ status: "stop_requested", id });
    } else {
      res.status(500).json({ error: "Failed to stop job" });
    }
  });

  // ── GET /api/processes/discover ─────────────────────────────────────────
  app.get("/api/processes/discover", (_req: Request, res: Response) => {
    res.json({
      runningJobs: registry.jobs.filter((j) => j.status === "running")
        .length,
      totalJobs: registry.jobs.length,
    });
  });
}

// ── Helpers ────────────────────────────────────────────────────────────────

export function buildAvailableCommandPayloads(commandMap: Map<string, CommandDefinition>) {
  return Array.from(commandMap.values()).map(({ build: _build, ...rest }) => rest);
}

export function buildCommandSchemaPayload(commandMap: Map<string, CommandDefinition>, npcKey: string) {
  const schemas: Record<
    string,
    { fields: Record<string, CommandFieldSchema>; cli?: CommandDefinition["cli"] }
  > = {};

  for (const [id, def] of commandMap.entries()) {
    const fields: Record<string, CommandFieldSchema> = {};

    for (const requiredField of def.requiredFields) {
      fields[requiredField] = {
        type: "string",
        required: true,
        description: `Required by ${id}`,
      };
    }

    const schema = def.schema;
    if (schema) {
      for (const [k, v] of Object.entries(schema)) {
        fields[k] = { ...fields[k], ...v };
      }
    }

    fields.commandId = {
      type: "string",
      required: true,
      default: id,
      description: "Backend command identifier",
    };

    schemas[id] = { fields, cli: def.cli };
  }

  return resolveTemplateDefaults(schemas, npcKey);
}

function resolveTemplateDefaults<T>(obj: T, npcKey: string): T {
  if (typeof obj === "string") {
    return obj.replace(/\{npcKey\}/g, npcKey) as T;
  }
  if (Array.isArray(obj)) {
    return obj.map((item) =>
      resolveTemplateDefaults(item, npcKey),
    ) as T;
  }
  if (obj && typeof obj === "object") {
    const resolved: Record<string, unknown> = {};
    for (const [key, value] of Object.entries(
      obj as Record<string, unknown>,
    )) {
      resolved[key] = resolveTemplateDefaults(value, npcKey);
    }
    return resolved as T;
  }
  return obj;
}
