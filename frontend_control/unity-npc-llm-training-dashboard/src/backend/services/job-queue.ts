import { type ChildProcessWithoutNullStreams } from "child_process";
import pg from "pg";
import crypto from "crypto";
import type {
  QueueJob,
  QueueOptions,
  QueueStats,
  JobProcessTracker,
} from "../types";
import { query, getPool } from "../lib/db";
import { logger } from "../lib/logger";
import { processJob, rowToQueueJob } from "./queue-worker";

// ── Defaults ───────────────────────────────────────────────────────────────

const DEFAULT_OPTIONS: QueueOptions = {
  concurrency: 2,
  pollIntervalMs: 2000,
  retryMax: 3,
  retryDelayBaseMs: 5000,
};

const STOP_ESCALATION_MS = 10_000;
const PID_HEALTH_INTERVAL_MS = 10_000;

// ── JobQueue ───────────────────────────────────────────────────────────────

/**
 * A lightweight PostgreSQL-backed job queue for the Unsloth_Core pipeline.
 *
 * - Persists every job state transition to the `pipeline_jobs` table.
 * - Polls the DB for pending jobs and spawns child processes up to a
 *   configurable concurrency limit.
 * - On failure, retries with exponential backoff (stored in metadata).
 * - Survives server restart: running jobs with dead PIDs are marked lost;
 *   running jobs with live PIDs are monitored.
 * - SIGTERM → SIGKILL escalation for cancellation.
 * - Designed as a drop-in conceptual replacement for BullMQ when Redis is
 *   unavailable.
 */
export class JobQueue {
  private readonly options: QueueOptions;
  private readonly pool: pg.Pool;

  // ── Active job tracking ────────────────────────────────────────────
  private readonly runningJobs = new Map<
    string,
    { process: ChildProcessWithoutNullStreams | null; stopRequested: boolean; terminal: boolean }
  >();
  private readonly stopEscalationTimers = new Map<string, NodeJS.Timeout>();

  // ── Polling state ──────────────────────────────────────────────────
  private pollTimer: ReturnType<typeof setInterval> | null = null;
  private healthTimer: ReturnType<typeof setInterval> | null = null;
  private isStopping = false;

  // ── Callbacks ──────────────────────────────────────────────────────
  private readonly updateCallbacks = new Set<(job: QueueJob) => void>();

  // ── Cached stats ───────────────────────────────────────────────────
  // Incrementally updated on job state transitions to avoid full-table
  // aggregate scans on every poll cycle. A full recount is triggered
  // every FULL_RECOUNT_INTERVAL transitions as a safety check.
  private cachedStats: QueueStats = {
    pending: 0,
    running: 0,
    completed: 0,
    failed: 0,
    stopped: 0,
    total: 0,
    activeWorkers: 0,
  };

  private readonly FULL_RECOUNT_INTERVAL = 50;
  private transitionCount = 0;

  // Tracks the last known status for each job so the onUpdate callback
  // can accurately detect state transitions and update cached stats.
  private readonly jobStatuses = new Map<string, string>();

  constructor(options?: Partial<QueueOptions>) {
    this.options = { ...DEFAULT_OPTIONS, ...options };
    this.pool = this.options.dbUrl
      ? new pg.Pool({ connectionString: this.options.dbUrl })
      : getPool();
  }

  // ── Public API ─────────────────────────────────────────────────────

  /**
   * Ensures the pipeline_jobs table exists (idempotent init).
   * Safe to call multiple times.
   */
  async init(): Promise<void> {
    await query(
      `CREATE TABLE IF NOT EXISTS pipeline_jobs (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        npc_key TEXT NOT NULL,
        type TEXT NOT NULL,
        command_id TEXT NOT NULL,
        command_args JSONB NOT NULL DEFAULT '[]',
        status TEXT NOT NULL DEFAULT 'pending'
          CHECK (status IN ('pending','running','completed','failed','stopped','paused')),
        progress INTEGER NOT NULL DEFAULT 0
          CHECK (progress >= 0 AND progress <= 100),
        loss REAL,
        exit_code INTEGER,
        error TEXT,
        wandb_url TEXT,
        workflow_id TEXT,
        chain_next JSONB,
        logs TEXT[] DEFAULT '{}',
        metadata JSONB DEFAULT '{}',
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        started_at TIMESTAMPTZ,
        finished_at TIMESTAMPTZ,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
      )`,
    );

    logger.info("Queue: pipeline_jobs table ensured");
  }

  /**
   * Enqueues a new job by inserting a row into pipeline_jobs.
   *
   * @returns The created QueueJob record.
   */
  async enqueue(
    npcKey: string,
    type: string,
    commandId: string,
    commandArgs: string[],
    jobOptions?: { cwd?: string; env?: Record<string, string> },
  ): Promise<QueueJob> {
    const id = crypto.randomUUID();
    const retryMax = this.options.retryMax;
    const retryDelayBaseMs = this.options.retryDelayBaseMs;

    const metadata: Record<string, unknown> = {
      retryCount: 0,
      retryMax,
      retryDelayBaseMs,
    };
    if (jobOptions?.cwd) metadata.cwd = jobOptions.cwd;
    if (jobOptions?.env) metadata.env = jobOptions.env;

    const rows = await query(
      `INSERT INTO pipeline_jobs (id, npc_key, type, command_id, command_args, status, metadata)
       VALUES ($1, $2, $3, $4, $5::jsonb, 'pending', $6::jsonb)
       RETURNING *`,
      [id, npcKey, type, commandId, JSON.stringify(commandArgs), JSON.stringify(metadata)],
    );

    const job = rowToQueueJob(rows[0]);
    this.adjustStats(null, "pending");
    logger.info("Queue: job enqueued", { jobId: job.id, npcKey, commandId });
    return job;
  }

  /**
   * Starts the polling loop and recovers any jobs that were running when the
   * server last stopped.
   */
  start(): void {
    if (this.pollTimer !== null) return; // already started

    this.isStopping = false;

    // ── Server restart recovery ─────────────────────────────────────
    this.recoverRunningJobs().catch((err) => {
      logger.error("Queue: recovery failed", {
        error: err instanceof Error ? err.message : String(err),
      });
    });

    // ── Polling loop — picks up pending jobs ────────────────────────
    this.pollTimer = setInterval(() => {
      this.poll().catch((err) => {
        logger.error("Queue: poll cycle failed", {
          error: err instanceof Error ? err.message : String(err),
        });
      });
    }, this.options.pollIntervalMs);

    // ── Health check for recovered processes ────────────────────────
    this.healthTimer = setInterval(() => {
      this.checkRecoveredProcessHealth().catch((err) => {
        logger.error("Queue: health check failed", {
          error: err instanceof Error ? err.message : String(err),
        });
      });
    }, PID_HEALTH_INTERVAL_MS);

    logger.info("Queue: started", {
      concurrency: this.options.concurrency,
      pollIntervalMs: this.options.pollIntervalMs,
    });
  }

  /**
   * Graceful stop. Waits for running jobs to finish, or sends SIGTERM after
   * the given timeout.
   *
   * @param timeoutMs - Max time (ms) to wait for running jobs before forcing
   *                    termination. 0 = no wait. Default: 30s.
   */
  async stop(timeoutMs = 30_000): Promise<void> {
    if (this.pollTimer === null) return; // not running

    this.isStopping = true;

    // Stop polling
    if (this.pollTimer !== null) {
      clearInterval(this.pollTimer);
      this.pollTimer = null;
    }
    if (this.healthTimer !== null) {
      clearInterval(this.healthTimer);
      this.healthTimer = null;
    }

    const activeJobIds = Array.from(this.runningJobs.keys());
    if (activeJobIds.length === 0) {
      logger.info("Queue: stopped (no active jobs)");
      return;
    }

    logger.info("Queue: stopping, waiting for jobs", {
      activeCount: activeJobIds.length,
      timeoutMs,
    });

    if (timeoutMs > 0) {
      // Wait for all active jobs to finish
      const start = Date.now();
      while (this.runningJobs.size > 0) {
        const elapsed = Date.now() - start;
        if (elapsed >= timeoutMs) break;
        await this.sleep(Math.min(500, timeoutMs - elapsed));
      }
    }

    // Force-terminate any remaining jobs
    for (const jobId of this.runningJobs.keys()) {
      await this.terminateJob(jobId);
    }

    logger.info("Queue: stopped");
  }

  /**
   * Fetches a single job by its UUID.
   */
  async getJob(jobId: string): Promise<QueueJob | null> {
    const rows = await query(
      `SELECT * FROM pipeline_jobs WHERE id = $1`,
      [jobId],
    );
    if (rows.length === 0) return null;
    return rowToQueueJob(rows[0]);
  }

  /**
   * Lists jobs with optional filters. Results ordered by created_at DESC.
   */
  async listJobs(
    filters?: {
      npcKey?: string;
      status?: string;
      limit?: number;
      offset?: number;
    },
  ): Promise<QueueJob[]> {
    const conditions: string[] = [];
    const params: unknown[] = [];
    let paramIndex = 0;

    if (filters?.npcKey) {
      paramIndex += 1;
      conditions.push(`npc_key = $${paramIndex}`);
      params.push(filters.npcKey);
    }
    if (filters?.status) {
      paramIndex += 1;
      conditions.push(`status = $${paramIndex}`);
      params.push(filters.status);
    }

    const whereClause =
      conditions.length > 0 ? `WHERE ${conditions.join(" AND ")}` : "";
    const limitVal = filters?.limit ?? 50;
    const offsetVal = filters?.offset ?? 0;

    paramIndex += 1;
    const limitParam = `$${paramIndex}`;
    params.push(limitVal);
    paramIndex += 1;
    const offsetParam = `$${paramIndex}`;
    params.push(offsetVal);

    const rows = await query(
      `SELECT * FROM pipeline_jobs ${whereClause}
       ORDER BY created_at DESC
       LIMIT ${limitParam} OFFSET ${offsetParam}`,
      params,
    );

    return rows.map(rowToQueueJob);
  }

  /**
   * Cancels a running job. Sends SIGTERM to the child process, escalates to
   * SIGKILL after STOP_ESCALATION_MS if the process does not exit.
   *
   * Updates the DB status to 'stopped' if the process was successfully killed.
   * Returns true if the job was located and a termination signal was sent.
   */
  async cancel(jobId: string): Promise<boolean> {
    const tracker = this.runningJobs.get(jobId);

    if (!tracker) {
      // Job might not be running (or tracked by this queue instance).
      // Try to stop via PID from DB metadata.
      const rows = await query(
        `SELECT metadata FROM pipeline_jobs WHERE id = $1 AND status = 'running'`,
        [jobId],
      );
      if (rows.length === 0) return false;
      const meta = rows[0].metadata as Record<string, unknown> | null;
      const pid = Number(meta?.pid);
      if (!Number.isFinite(pid)) return false;

      // Send SIGTERM to the orphaned process
      try {
        process.kill(pid, "SIGTERM");
      } catch {
        return false;
      }

      // Update DB status
      this.adjustStats("running", "stopped");
      await query(
        `UPDATE pipeline_jobs
         SET status = 'stopped',
             exit_code = -15,
             error = 'Job cancelled via queue',
             finished_at = NOW(),
             updated_at = NOW()
         WHERE id = $1`,
        [jobId],
      );

      logger.info("Queue: cancelled orphaned job by PID", { jobId, pid });
      return true;
    }

    // ── Job is tracked in this queue instance ──────────────────────
    tracker.stopRequested = true;

    const proc = tracker.process;
    if (!proc || !proc.pid) {
      // No process handle — mark DB but can't send signal
      this.adjustStats("running", "stopped");
      await query(
        `UPDATE pipeline_jobs
         SET status = 'stopped',
             exit_code = -15,
             error = 'Job cancelled (no process handle)',
             finished_at = NOW(),
             updated_at = NOW()
         WHERE id = $1`,
        [jobId],
      );
      return true;
    }

    // SIGTERM — try negative PID (process group) first, then direct
    try {
      process.kill(-proc.pid, "SIGTERM");
    } catch {
      try {
        proc.kill("SIGTERM");
      } catch {
        // Process may already be dead
      }
    }

    // Escalation timer: SIGKILL after timeout
    if (!this.stopEscalationTimers.has(jobId)) {
      const timer = setTimeout(() => {
        const p = this.runningJobs.get(jobId)?.process;
        if (!p) {
          this.stopEscalationTimers.delete(jobId);
          return;
        }
        try {
          process.kill(-p.pid!, "SIGKILL");
        } catch {
          try {
            p.kill("SIGKILL");
          } catch {
            // Already dead
          }
        }
        this.stopEscalationTimers.delete(jobId);
      }, STOP_ESCALATION_MS);
      this.stopEscalationTimers.set(jobId, timer);
    }

    logger.info("Queue: cancel sent SIGTERM", { jobId });
    return true;
  }

  /**
   * Retries a failed (or stopped) job by resetting its status to 'pending'
   * and clearing the finished_at timestamp.
   *
   * Returns the updated job, or null if the job was not found or not eligible
   * for retry.
   */
  async retry(jobId: string): Promise<QueueJob | null> {
    // Read current status so we can correctly adjust incremental stats
    const before = await query(
      `SELECT status FROM pipeline_jobs WHERE id = $1`,
      [jobId],
    );

    const rows = await query(
      `UPDATE pipeline_jobs
       SET status = 'pending',
           error = NULL,
           exit_code = NULL,
           finished_at = NULL,
           progress = 0,
           metadata = jsonb_set(
             jsonb_set(COALESCE(metadata, '{}'), '{retryCount}', '0'::jsonb),
             '{nextRetryAt}',
             'null'::jsonb
           ),
           updated_at = NOW()
       WHERE id = $1
         AND status IN ('failed', 'stopped')
       RETURNING *`,
      [jobId],
    );

    if (rows.length === 0) return null;

    // Adjust incremental stats: decrement the source bucket,
    // increment 'pending'
    const prevStatus = before.length > 0 ? String(before[0].status) : null;
    if (prevStatus) {
      this.adjustStats(prevStatus, "pending");
    }

    const job = rowToQueueJob(rows[0]);
    logger.info("Queue: job queued for retry", { jobId });
    return job;
  }

  /**
   * Returns the current queue statistics.
   */
  getStats(): QueueStats {
    return { ...this.cachedStats, activeWorkers: this.runningJobs.size };
  }

  /**
   * Registers a callback that fires on every meaningful job state change
   * (status, progress, loss). Useful for WebSocket broadcasts.
   */
  onUpdate(callback: (job: QueueJob) => void): void {
    this.updateCallbacks.add(callback);
  }

  /**
   * Removes (archives) jobs that are terminal (completed, failed, stopped)
   * and older than the given number of days. Returns the number of rows
   * deleted.
   */
  async clean(maxAgeDays = 7): Promise<number> {
    const rows = await query(
      `DELETE FROM pipeline_jobs
       WHERE status IN ('completed', 'failed', 'stopped')
         AND finished_at < NOW() - ($1 || ' days')::INTERVAL
       RETURNING id`,
      [String(maxAgeDays)],
    );

    const count = rows.length;
    if (count > 0) {
      logger.info("Queue: cleaned old jobs", { count, maxAgeDays });
    }
    return count;
  }

  // ── Internal: Polling ──────────────────────────────────────────────

  /**
   * One poll cycle: fetch pending jobs and start new ones up to the
   * concurrency limit.
   *
   * Stats are updated incrementally on job state transitions rather than
   * via a full-table aggregate query every cycle. A full recount is
   * triggered automatically from `adjustStats` every FULL_RECOUNT_INTERVAL
   * transitions as a safety check.
   */
  private async poll(): Promise<void> {
    if (this.isStopping) return;

    const available = this.options.concurrency - this.runningJobs.size;
    if (available <= 0) return;

    // Fetch pending jobs that are eligible (no retry delay, or delay passed)
    const pendingRows = await query(
      `SELECT * FROM pipeline_jobs
       WHERE status = 'pending'
         AND (
           metadata->>'nextRetryAt' IS NULL
           OR metadata->>'nextRetryAt' = 'null'
           OR (metadata->>'nextRetryAt')::TIMESTAMPTZ <= NOW()
         )
       ORDER BY created_at ASC
       LIMIT $1
       FOR UPDATE SKIP LOCKED`,
      [available],
    );

    for (const row of pendingRows) {
      if (this.runningJobs.size >= this.options.concurrency) break;

      const job = rowToQueueJob(row);
      this.startJobProcess(job).catch((err) => {
        logger.error("Queue: process start failed", {
          jobId: job.id,
          error: err instanceof Error ? err.message : String(err),
        });
      });
    }
  }

  /**
   * Wraps processJob with tracking, lifecycle management, and cleanup.
   * Detects job state transitions and updates cachedStats incrementally.
   */
  private async startJobProcess(job: QueueJob): Promise<void> {
    const tracker: JobProcessTracker = {
      process: null,
      stopRequested: false,
      terminal: false,
    };

    this.runningJobs.set(job.id, tracker);
    this.jobStatuses.set(job.id, job.status);

    try {
      await processJob(job, this.pool, tracker, (updatedJob) => {
        // Detect state transitions for incremental stats update
        const prevStatus = this.jobStatuses.get(job.id);
        if (prevStatus && prevStatus !== updatedJob.status) {
          this.adjustStats(prevStatus, updatedJob.status);
        }
        this.jobStatuses.set(job.id, updatedJob.status);
        this.notifyUpdateCallbacks(updatedJob);
      });
    } finally {
      this.jobStatuses.delete(job.id);
      this.cleanupJob(job.id);
    }
  }

  /**
   * Removes a job from the active tracking maps and clears escalation timers.
   */
  private cleanupJob(jobId: string): void {
    this.runningJobs.delete(jobId);

    const timer = this.stopEscalationTimers.get(jobId);
    if (timer) {
      clearTimeout(timer);
      this.stopEscalationTimers.delete(jobId);
    }
  }

  // ── Internal: Restart Recovery ─────────────────────────────────────

  /**
   * On startup, finds all jobs in 'running' state and either:
   * - Marks them as 'failed' if the PID is dead (server restart lost the process).
   * - Leaves them as 'running' if the PID is alive (will be monitored).
   */
  private async recoverRunningJobs(): Promise<void> {
    const rows = await query(
      `SELECT * FROM pipeline_jobs WHERE status = 'running'`,
    );

    if (rows.length === 0) return;

    logger.info("Queue: recovering running jobs", { count: rows.length });

    for (const row of rows) {
      const job = rowToQueueJob(row);
      const meta = (row.metadata ?? {}) as Record<string, unknown>;
      const pid = Number(meta.pid);

      if (!Number.isFinite(pid)) {
        // No PID stored — cannot recover
        await this.markLost(job.id, "No process ID recorded");
        continue;
      }

      const isAlive = this.isPidAlive(pid);
      if (isAlive) {
        // Process survived the restart
        await query(
          `UPDATE pipeline_jobs
           SET metadata = jsonb_set(COALESCE(metadata, '{}'), '{recoveredAt}', $2::jsonb),
               updated_at = NOW()
           WHERE id = $1`,
          [job.id, JSON.stringify(new Date().toISOString())],
        );

        logger.info("Queue: recovered running job (PID alive)", {
          jobId: job.id,
          pid,
        });
      } else {
        await this.markLost(job.id, `Server restarted — job lost (PID ${pid} not found)`);
      }
    }
  }

  /**
   * Periodically checks recovered processes for liveness. If a process that
   * we're tracking has died (without us seeing its exit code), we mark it
   * as failed.
   */
  private async checkRecoveredProcessHealth(): Promise<void> {
    for (const [jobId, tracker] of this.runningJobs) {
      if (tracker.terminal) continue; // already finalized by processJob

      const proc = tracker.process;
      if (!proc) continue; // not yet spawned, skip

      // If we have a process reference, it's actively being monitored by
      // processJob. The 'close' event will fire when it exits.
      // This check is for recovered processes that we're tracking by PID alone.
    }

    // Also check DB for processes that have a PID but no process reference
    const rows = await query(
      `SELECT id, metadata FROM pipeline_jobs
       WHERE status = 'running'
         AND metadata->>'pid' IS NOT NULL`,
    );

    for (const row of rows) {
      const jobId = String(row.id);
      if (this.runningJobs.has(jobId)) continue; // being monitored actively

      const meta = (row.metadata ?? {}) as Record<string, unknown>;
      const pid = Number(meta.pid);

      if (!Number.isFinite(pid)) continue;

      if (!this.isPidAlive(pid)) {
        await this.markLost(jobId, `Process PID ${pid} died — marked lost`);
      }
    }
  }

  /**
   * Marks a job as 'failed' in the DB with the given error message.
   */
  private async markLost(jobId: string, error: string): Promise<void> {
    this.adjustStats("running", "failed");
    await query(
      `UPDATE pipeline_jobs
       SET status = 'failed',
           exit_code = -1,
           error = $2,
           finished_at = NOW(),
           updated_at = NOW()
       WHERE id = $1`,
      [jobId, error],
    );

    logger.warn("Queue: job marked lost", { jobId, error });
  }

  // ── Internal: Helpers ─────────────────────────────────────────────

  /**
   * Checks whether a process ID is alive using signal 0.
   */
  private isPidAlive(pid: number): boolean {
    try {
      process.kill(pid, 0);
      return true;
    } catch {
      return false;
    }
  }

  /**
   * Force-terminates a tracked job with SIGKILL escalation.
   */
  private async terminateJob(jobId: string): Promise<void> {
    const tracker = this.runningJobs.get(jobId);
    if (!tracker) return;

    tracker.stopRequested = true;
    const proc = tracker.process;

    if (proc?.pid) {
      try {
        process.kill(-proc.pid, "SIGTERM");
      } catch {
        try {
          proc.kill("SIGTERM");
        } catch {
          // ignore
        }
      }

      // Short wait then SIGKILL
      await this.sleep(2000);
      try {
        process.kill(-proc.pid, "SIGKILL");
      } catch {
        try {
          proc.kill("SIGKILL");
        } catch {
          // ignore
        }
      }
    }

    await query(
      `UPDATE pipeline_jobs
       SET status = 'stopped',
           exit_code = -9,
           error = 'Server shutdown — job terminated',
           finished_at = NOW(),
           updated_at = NOW()
       WHERE id = $1`,
      [jobId],
    );

    this.cleanupJob(jobId);
    logger.info("Queue: job force-terminated on stop", { jobId });
  }

  /**
   * Refreshes the cached stats by querying the DB.
   * Called as a safety check every FULL_RECOUNT_INTERVAL transitions.
   */
  private async refreshStats(): Promise<void> {
    try {
      const rows = await query(
        `SELECT status, COUNT(*)::int AS count
         FROM pipeline_jobs
         GROUP BY status`,
      );

      const counts: Record<string, number> = {};
      for (const row of rows) {
        counts[String(row.status)] = Number(row.count);
      }

      this.cachedStats = {
        pending: counts.pending ?? 0,
        running: counts.running ?? 0,
        completed: counts.completed ?? 0,
        failed: counts.failed ?? 0,
        stopped: counts.stopped ?? 0,
        total: Object.values(counts).reduce((a, b) => a + b, 0),
        activeWorkers: this.runningJobs.size,
      };

      this.transitionCount = 0;
    } catch (err) {
      logger.error("Queue: failed to refresh stats", {
        error: err instanceof Error ? err.message : String(err),
      });
    }
  }

  /**
   * Incrementally updates cachedStats when a job transitions between states.
   * Triggers a full recount every FULL_RECOUNT_INTERVAL transitions as a
   * safety check against drift.
   */
  private adjustStats(fromStatus: string | null, toStatus: string): void {
    if (fromStatus === toStatus) return;

    this.transitionCount++;

    // Decrement the source bucket
    switch (fromStatus) {
      case "pending":  this.cachedStats.pending--; break;
      case "running":  this.cachedStats.running--; break;
      case "completed": this.cachedStats.completed--; break;
      case "failed":   this.cachedStats.failed--; break;
      case "stopped":  this.cachedStats.stopped--; break;
      // 'null' means it's a newly created job — nothing to decrement
    }

    // Increment the target bucket
    switch (toStatus) {
      case "pending":  this.cachedStats.pending++; break;
      case "running":  this.cachedStats.running++; break;
      case "completed": this.cachedStats.completed++; break;
      case "failed":   this.cachedStats.failed++; break;
      case "stopped":  this.cachedStats.stopped++; break;
    }

    this.cachedStats.total =
      this.cachedStats.pending +
      this.cachedStats.running +
      this.cachedStats.completed +
      this.cachedStats.failed +
      this.cachedStats.stopped;

    // Full recount safety check
    if (this.transitionCount >= this.FULL_RECOUNT_INTERVAL) {
      this.transitionCount = 0;
      this.refreshStats().catch((err) => {
        logger.error("Queue: periodic stats recount failed", {
          error: err instanceof Error ? err.message : String(err),
        });
      });
    }
  }

  /**
   * Fires all registered update callbacks with the latest job state.
   */
  private notifyUpdateCallbacks(job: QueueJob): void {
    for (const cb of this.updateCallbacks) {
      try {
        cb(job);
      } catch (err) {
        logger.error("Queue: update callback error", {
          error: err instanceof Error ? err.message : String(err),
        });
      }
    }
  }

  /**
   * Promise-based sleep.
   */
  private sleep(ms: number): Promise<void> {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }
}
