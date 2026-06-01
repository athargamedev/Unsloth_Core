import type { Express, Request, Response } from "express";
import path from "path";
import fs from "fs";
import type { RouterDependencies, PipelineRunRecord } from "../types";

const CANONICAL_STAGE_ORDER = ["generate", "sanitize", "dataset_eval", "train", "export", "evaluate"] as const;
const STAGE_OUTPUT_ARTIFACTS: Record<string, string[]> = {
  generate: ["dataset_raw"],
  sanitize: ["dataset_clean"],
  dataset_eval: ["quality_summary"],
  train: ["adapter_checkpoint"],
  export: ["gguf_adapter"],
  evaluate: ["eval_index"],
};
const STAGE_REQUIRED_ARTIFACTS: Record<string, string[]> = {
  generate: [],
  sanitize: ["dataset_raw"],
  dataset_eval: ["dataset_clean"],
  train: ["dataset_clean", "quality_summary"],
  export: ["adapter_checkpoint"],
  evaluate: ["gguf_adapter"],
};

interface ArtifactRecord {
  ts?: string;
  npc_key?: string;
  technique?: string | null;
  stage?: string;
  artifact_type?: string;
  path?: string;
  sha256?: string | null;
  metadata?: Record<string, unknown>;
  [key: string]: unknown;
}

/**
 * Registers /api/pipeline/* routes.
 */
export function registerRoutes(app: Express, deps: RouterDependencies): void {
  const { repoRoot } = deps;

  const pipelineRoot = path.join(repoRoot, ".pipeline");
  const pipelineRunsRoot = path.join(pipelineRoot, "runs");
  const pipelineIndexPath = path.join(pipelineRoot, "runs.jsonl");
  const artifactIndexPath = path.join(pipelineRoot, "artifacts.jsonl");

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

  function readArtifactRecords(
    limit = 2000,
    npcKey?: string,
    technique?: string | null,
  ): ArtifactRecord[] {
    return readTailLines(artifactIndexPath, limit * 2)
      .map((line) => {
        try {
          return JSON.parse(line) as ArtifactRecord;
        } catch {
          return null;
        }
      })
      .filter((record): record is ArtifactRecord => Boolean(record))
      .filter((record) => !npcKey || record.npc_key === npcKey)
      .filter((record) => technique === undefined || record.technique === technique)
      .slice(-limit);
  }

  function latestArtifact(records: ArtifactRecord[], artifactType: string): ArtifactRecord | null {
    for (let index = records.length - 1; index >= 0; index -= 1) {
      if (records[index]?.artifact_type === artifactType) return records[index];
    }
    return null;
  }

  function producerFor(artifactType: string): string | null {
    for (const [stage, outputs] of Object.entries(STAGE_OUTPUT_ARTIFACTS)) {
      if (outputs.includes(artifactType)) return stage;
    }
    return null;
  }

  function buildReadinessPlan(
    npcKey: string,
    targetStage: string,
    technique?: string | null,
  ) {
    const normalizedTarget = targetStage || "evaluate";
    if (!CANONICAL_STAGE_ORDER.includes(normalizedTarget as typeof CANONICAL_STAGE_ORDER[number])) {
      return { error: `Unknown pipeline stage: ${normalizedTarget}` };
    }
    const records = readArtifactRecords(2000, npcKey, technique);
    const targetIndex = CANONICAL_STAGE_ORDER.indexOf(normalizedTarget as typeof CANONICAL_STAGE_ORDER[number]);
    const steps = CANONICAL_STAGE_ORDER.slice(0, targetIndex + 1).map((stage) => {
      const missingArtifacts = (STAGE_REQUIRED_ARTIFACTS[stage] ?? []).filter(
        (artifactType) => latestArtifact(records, artifactType) === null,
      );
      const producedArtifacts = Object.fromEntries(
        (STAGE_OUTPUT_ARTIFACTS[stage] ?? []).map((artifactType) => [artifactType, latestArtifact(records, artifactType)]),
      );
      return {
        stage,
        ready: missingArtifacts.length === 0,
        missing_artifacts: missingArtifacts,
        missing_stages: missingArtifacts.map(producerFor).filter(Boolean),
        produces: STAGE_OUTPUT_ARTIFACTS[stage] ?? [],
        artifacts: producedArtifacts,
      };
    });
    const nextRequiredStage = steps.find((step) => Object.values(step.artifacts).every((artifact) => artifact === null))?.stage ?? null;
    return {
      npc_key: npcKey,
      technique: technique ?? null,
      target_stage: normalizedTarget,
      ready: steps.every((step) => step.ready),
      next_required_stage: nextRequiredStage,
      artifact_registry_path: artifactIndexPath,
      artifact_count: records.length,
      steps,
    };
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

  // ── GET /api/pipeline/readiness ─────────────────────────────────────────
  app.get("/api/pipeline/readiness", (req: Request, res: Response) => {
    const npcKey = typeof req.query.npc_key === "string" ? req.query.npc_key : undefined;
    const technique = typeof req.query.technique === "string" ? req.query.technique : undefined;
    const targetStage = typeof req.query.target_stage === "string" ? req.query.target_stage : "evaluate";
    if (!npcKey) {
      res.status(400).json({ error: "npc_key is required" });
      return;
    }
    const plan = buildReadinessPlan(npcKey, targetStage, technique);
    if ("error" in plan) {
      res.status(400).json(plan);
      return;
    }
    res.json(plan);
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
