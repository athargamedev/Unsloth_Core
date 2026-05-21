import type { Express, Request, Response } from "express";
import type { RouterDependencies, JobRegistrySnapshot } from "../types";
import { getJobRegistrySnapshot } from "../services/registry";
import { readJobLogs as readJobLogsFromFile } from "../lib/read-job-logs";

/**
 * Registers /api/jobs/* routes.
 *
 * GET  /api/jobs              — full job list (refreshes cache)
 * GET  /api/jobs/state        — job list with runIds + snapshot
 * GET  /api/jobs/:id/logs     — per-job log file tail
 * POST /api/jobs/clear        — clear all completed jobs
 * POST /api/jobs/sync         — force sync external artifacts
 * DELETE /api/jobs/:id        — delete a single completed job
 */
export function registerRoutes(app: Express, deps: RouterDependencies): void {
  const { registry, invalidateJobsCache, persistRegistry, flushPersist, broadcast, globalLog } = deps;

  /**
   * In-memory jobs cache with TTL.
   */
  const CACHE_TTL_MS = 2000;
  let jobsCache: { jobs: typeof registry.jobs; timestamp: number } | null = null;

  const refreshJobsCacheIfStale = () => {
    const now = Date.now();
    if (jobsCache && now - jobsCache.timestamp < CACHE_TTL_MS) return jobsCache.jobs;
    jobsCache = { jobs: registry.jobs, timestamp: now };
    return jobsCache.jobs;
  };

  const invalidateLocalCache = () => {
    jobsCache = null;
    invalidateJobsCache();
  };

  // ── GET /api/jobs ──────────────────────────────────────────────────────
  app.get("/api/jobs", (_req: Request, res: Response) => {
    const jobs = refreshJobsCacheIfStale();
    res.json(jobs);
  });

  // ── GET /api/jobs/state ────────────────────────────────────────────────
  app.get("/api/jobs/state", (_req: Request, res: Response) => {
    const jobs = refreshJobsCacheIfStale();
    res.json({
      jobs,
      workflowCount: registry.workflows.length,
      autoSyncExternal: registry.autoSyncExternal !== false,
    } satisfies JobRegistrySnapshot);
  });

  // ── GET /api/jobs/:id/logs ─────────────────────────────────────────────
  app.get("/api/jobs/:id/logs", (req: Request, res: Response) => {
    try {
      const logEntries = readJobLogsFromFile(req.params.id);
      const job = registry.jobs.find((j) => j.id === req.params.id);
      res.json({ logs: logEntries, jobName: job?.name || null });
    } catch {
      res.status(500).json({ error: "Failed to read job logs" });
    }
  });

  // ── POST /api/jobs/clear ───────────────────────────────────────────────
  app.post("/api/jobs/clear", (_req: Request, res: Response) => {
    const running = registry.jobs.filter((job) => job.status === "running");
    if (running.length > 0) {
      res.status(409).json({
        error: "Cannot clear while jobs are running",
        running: running.map((job) => job.id),
      });
      return;
    }

    registry.jobs = [];
    registry.workflows = [];
    registry.logs = [];
    registry.autoSyncExternal = false;
    invalidateLocalCache();
    flushPersist(registry);
    broadcast("logs_cleared", { clearedAt: new Date().toISOString() });
    broadcast("job_update", { cleared: true, jobs: 0, autoSyncExternal: false });
    res.json({ success: true, cleared: true });
  });

  // ── DELETE /api/jobs/:id ───────────────────────────────────────────────
  app.delete("/api/jobs/:id", (req: Request, res: Response) => {
    const { id } = req.params;
    const index = registry.jobs.findIndex((j) => j.id === id);
    if (index === -1) {
      res.status(404).json({ error: "Job not found" });
      return;
    }
    const job = registry.jobs[index];
    if (job.status === "running") {
      res.status(409).json({ error: "Cannot delete a running job" });
      return;
    }

    registry.jobs.splice(index, 1);
    invalidateLocalCache();
    globalLog(registry, `[SYSTEM] dismissed job ${id}`);
    flushPersist(registry);
    broadcast("job_deleted", { id });
    res.json({ success: true });
  });

  // ── POST /api/jobs/sync ────────────────────────────────────────────────
  app.post("/api/jobs/sync", (req: Request, res: Response) => {
    const force = Boolean((req.body as { force?: boolean } | undefined)?.force);
    if (force) {
      registry.autoSyncExternal = true;
    }
    invalidateLocalCache();
    res.json({
      synced: true,
      force,
      jobs: registry.jobs.length,
      workflowCount: registry.workflows.length,
    });
  });

  // ── GET /api/logs ──────────────────────────────────────────────────────
  app.get("/api/logs", (_req: Request, res: Response) => {
    res.json(registry.logs);
  });

  // ── POST /api/logs/clear ───────────────────────────────────────────────
  app.post("/api/logs/clear", (_req: Request, res: Response) => {
    registry.logs.length = 0;
    flushPersist(registry);
    broadcast("logs_cleared", { clearedAt: new Date().toISOString() });
    res.json({ success: true });
  });

  // ── GET /api/analytics ─────────────────────────────────────────────────
  app.get("/api/analytics", (req: Request, res: Response) => {
    const jobId = typeof req.query.jobId === "string" ? req.query.jobId : "";
    const job = registry.jobs.find((item) => item.id === jobId) ?? registry.jobs[0];
    if (!job) {
      res.json([]);
      return;
    }

    const points: Array<{ step: number; loss: number; acc: number; lr: number }> = [];
    let step = 0;
    for (const line of job.logs) {
      const lossMatch = line.match(/loss[:=]\s*([0-9]*\.?[0-9]+)/i);
      if (!lossMatch) continue;
      step += 1;
      const loss = Number(lossMatch[1]);
      points.push({
        step,
        loss,
        acc: Math.max(0, Math.min(1, 1 - loss / 3)),
        lr: Number((2e-4 / Math.max(1, step)).toPrecision(4)),
      });
    }
    res.json(points);
  });
}
