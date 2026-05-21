import path from "node:path";
import fs from "node:fs";
import type { Express, Request, Response } from "express";
import type { RouterDependencies, StartCommandPayload, Job } from "../types";
import { launchJob, stopJob, updateStagesFromTruth, makeId, isoNow } from "../services/job-runner";
import { validateRequiredFields } from "../lib/validation";

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
    const defs = Array.from(commandMap.values()).map(
      ({ build, ...rest }) => rest,
    );
    res.json(defs);
  });

  // ── GET /api/command-schemas ────────────────────────────────────────────
  app.get("/api/command-schemas", (req: Request, res: Response) => {
    const npcKey =
      String(req.query.npcKey || "history_guide").trim() ||
      "history_guide";

    type FieldSchema = {
      type: "string" | "number" | "boolean";
      required: boolean;
      default?: string | number | boolean;
      description?: string;
      enum?: string[];
    };

    const DEFAULT_BASE_MODEL =
      process.env.DEFAULT_BASE_MODEL ||
      "unsloth/Llama-3.2-3B-Instruct-bnb-4bit";

    // Load presets for enum options
    const presetsDir = path.join(
      repoRoot,
      "configs",
      "presets",
    );
    const presetOptions: string[] = [];
    try {
      if (fs.existsSync(presetsDir)) {
        for (const file of fs.readdirSync(presetsDir)) {
          if (
            !(
              file.endsWith(".yaml") || file.endsWith(".yml")
            )
          )
            continue;
          presetOptions.push(
            file.replace(/\.ya?ml$/, ""),
          );
        }
      }
    } catch {
      // presets dir may not exist
    }

    const baseDefaultsByCommand: Record<
      string,
      Record<string, FieldSchema>
    > = {
      "dataset-generate": {
        spec: {
          type: "string",
          required: true,
          default: "subjects/NPC_specs/{npcKey}.json",
          description: "Subject spec path",
        },
        "options.technique": {
          type: "string",
          required: false,
          default: "template",
          enum: [
            "template",
            "docs",
            "ollama",
            "openai",
            "anthropic",
          ],
        },
      },
      train: {
        spec: {
          type: "string",
          required: true,
          default: "subjects/NPC_specs/{npcKey}.json",
        },
        preset: {
          type: "string",
          required: false,
          default: "fast-3b",
          ...(presetOptions.length
            ? { enum: presetOptions }
            : {}),
        },
        "options.learningRate": {
          type: "string",
          required: false,
          default: "2e-4",
        },
        "options.batchSize": {
          type: "number",
          required: false,
          default: 1,
        },
        "options.epochs": {
          type: "number",
          required: false,
          default: 3,
        },
        "options.rank": {
          type: "number",
          required: false,
          default: 16,
        },
        "options.alpha": {
          type: "number",
          required: false,
          default: 32,
        },
        "options.baseModel": {
          type: "string",
          required: false,
          default: DEFAULT_BASE_MODEL,
        },
        "options.technique": {
          type: "string",
          required: false,
          default: "template",
          enum: [
            "template",
            "docs",
            "ollama",
            "openai",
            "anthropic",
          ],
        },
        "options.wandb": {
          type: "boolean",
          required: false,
          default: false,
        },
      },
      pipeline: {
        spec: {
          type: "string",
          required: true,
          default: "subjects/NPC_specs/{npcKey}.json",
        },
        preset: {
          type: "string",
          required: false,
          default: "fast-3b",
          ...(presetOptions.length
            ? { enum: presetOptions }
            : {}),
        },
        "options.technique": {
          type: "string",
          required: false,
          default: "template",
          enum: [
            "template",
            "docs",
            "ollama",
            "openai",
            "anthropic",
          ],
        },
        "options.track": {
          type: "boolean",
          required: false,
          default: false,
        },
        "options.wandb": {
          type: "boolean",
          required: false,
          default: false,
        },
      },
    };

    const schemas: Record<
      string,
      { fields: Record<string, FieldSchema> }
    > = {};

    for (const [id, def] of commandMap.entries()) {
      const fields: Record<string, FieldSchema> = {};

      for (const requiredField of def.requiredFields) {
        fields[requiredField] = {
          type: "string",
          required: true,
          description: `Required by ${id}`,
        };
      }

      const defaults = baseDefaultsByCommand[id] || {};
      for (const [k, v] of Object.entries(defaults)) {
        fields[k] = { ...fields[k], ...v };
      }

      fields.commandId = {
        type: "string",
        required: true,
        default: id,
        description: "Backend command identifier",
      };

      schemas[id] = { fields };
    }

    // Resolve {npcKey} templates
    const resolved = resolveTemplateDefaults(schemas, npcKey);
    res.json(resolved);
  });

  // ── POST /api/commands/start ────────────────────────────────────────────
  app.post("/api/commands/start", (req: Request, res: Response) => {
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
  app.post("/api/commands/stop", (req: Request, res: Response) => {
    const { id } = req.body as { id?: string };
    if (!id) {
      res.status(400).json({ error: "id is required" });
      return;
    }

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
