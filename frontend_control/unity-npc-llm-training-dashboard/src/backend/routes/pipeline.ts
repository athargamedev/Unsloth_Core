import type { Express, Request, Response } from "express";
import path from "path";
import fs from "fs";
import type { RouterDependencies, PipelineRunRecord } from "../types";

/**
 * Registers /api/pipeline/* routes.
 */
export function registerRoutes(app: Express, deps: RouterDependencies): void {
  const { repoRoot } = deps;

  const pipelineRoot = path.join(repoRoot, ".pipeline");
  const pipelineRunsRoot = path.join(pipelineRoot, "runs");
  const pipelineIndexPath = path.join(pipelineRoot, "runs.jsonl");

  function readTailLines(filePath: string, maxLines = 40): string[] {
    try {
      if (!fs.existsSync(filePath)) return [];
      return fs
        .readFileSync(filePath, "utf8")
        .split("\n")
        .filter(Boolean)
        .slice(-maxLines);
    } catch {
      return [];
    }
  }

  function readPipelineRunRecords(
    limit = 200,
    npcKey?: string,
    stage?: string,
  ): PipelineRunRecord[] {
    const lines = readTailLines(pipelineIndexPath, limit * 3);
    const records = lines
      .map((line) => {
        try {
          return JSON.parse(line) as PipelineRunRecord;
        } catch {
          return null;
        }
      })
      .filter((record): record is PipelineRunRecord => Boolean(record))
      .filter((record) => !npcKey || record.npc_key === npcKey)
      .filter((record) => !stage || record.stage === stage);
    return records.slice(-limit);
  }

  function readPipelineRunEvents(runId: string): PipelineRunRecord[] {
    return readPipelineRunRecords(1000).filter((record) => record.run_id === runId);
  }

  function readPipelineRunHooks(runId: string) {
    return readTailLines(path.join(pipelineRunsRoot, runId, "workflow_hooks.jsonl"), 1000)
      .map((line) => {
        try {
          return JSON.parse(line);
        } catch {
          return null;
        }
      })
      .filter(Boolean);
  }

  function readPipelineRunLog(runId: string) {
    return readTailLines(path.join(pipelineRunsRoot, runId, "log_state.jsonl"), 1000);
  }

  // ── GET /api/pipeline/runs ─────────────────────────────────────────────
  app.get("/api/pipeline/runs", (req: Request, res: Response) => {
    const npcKey = typeof req.query.npc_key === "string" ? req.query.npc_key : undefined;
    const stage = typeof req.query.stage === "string" ? req.query.stage : undefined;
    const limit = Number.parseInt(
      typeof req.query.limit === "string" ? req.query.limit : "50",
      10,
    );
    const records = readPipelineRunRecords(
      Number.isFinite(limit) ? limit : 50,
      npcKey,
      stage,
    );
    res.json({ runs: records, total_events: records.length });
  });

  // ── GET /api/pipeline/runs/:run_id ─────────────────────────────────────
  app.get("/api/pipeline/runs/:run_id", (req: Request, res: Response) => {
    const runId = req.params.run_id;
    const events = readPipelineRunEvents(runId);
    const runDir = path.join(pipelineRunsRoot, runId);
    const metaPath = path.join(runDir, "meta.json");
    const meta = readJsonFile<Record<string, unknown>>(metaPath, {});
    res.json({
      run: meta,
      events,
      hooks: readPipelineRunHooks(runId),
      log: readPipelineRunLog(runId),
    });
  });

  app.get("/api/pipeline/runs/:run_id/hooks", (req: Request, res: Response) => {
    res.json({ events: readPipelineRunHooks(req.params.run_id) });
  });

  app.get("/api/pipeline/runs/:run_id/log", (req: Request, res: Response) => {
    res.json({ lines: readPipelineRunLog(req.params.run_id) });
  });

  // ── GET /api/npc/:npc_key/status ───────────────────────────────────────
  app.get("/api/npc/:npc_key/status", (req: Request, res: Response) => {
    const npcKey = req.params.npc_key;
    const records = readPipelineRunRecords(1000, npcKey);

    const latestComplete: Record<string, PipelineRunRecord> = {};
    const latestError: Record<string, PipelineRunRecord> = {};
    for (const record of records) {
      const stage = record.stage || "";
      if (record.event === "complete") latestComplete[stage] = record;
      if (record.event === "error") latestError[stage] = record;
    }

    const stages = [
      "generate",
      "sanitize",
      "dataset_eval",
      "train",
      "export",
      "evaluate",
      "feedback",
    ];
    const completedCore = ["generate", "sanitize", "dataset_eval", "train", "export"].filter(
      (stage) => latestComplete[stage],
    ).length;
    const hasErrors = Object.keys(latestError).length > 0;
    const pipelineHealth =
      completedCore === 5 ? "healthy" : completedCore > 0 && !hasErrors ? "partial" : hasErrors ? "error" : "empty";

    res.json({
      npc_key: npcKey,
      pipeline_health: pipelineHealth,
      stages: Object.fromEntries(
        stages.map((stage) => [
          stage,
          {
            latest_complete: latestComplete[stage] ?? null,
            latest_error: latestError[stage] ?? null,
          },
        ]),
      ),
    });
  });
}

function readJsonFile<T>(filePath: string, fallback: T): T {
  try {
    if (!fs.existsSync(filePath)) return fallback;
    return JSON.parse(fs.readFileSync(filePath, "utf8")) as T;
  } catch {
    return fallback;
  }
}
