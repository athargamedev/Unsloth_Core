import { spawn } from "child_process";
import pg from "pg";
import type { QueueJob, JobProcessTracker } from "../types";
import { query } from "../lib/db";
import { logger } from "../lib/logger";

// ── Constants ──────────────────────────────────────────────────────────────

const LOG_FLUSH_INTERVAL_MS = 1000;

// ── Row Mapping ────────────────────────────────────────────────────────────

/**
 * Maps a snake_case pipeline_jobs DB row to a camelCase QueueJob.
 */
function rowToQueueJob(row: Record<string, unknown>): QueueJob {
  return {
    id: String(row.id),
    npcKey: String(row.npc_key),
    type: String(row.type),
    commandId: String(row.command_id),
    commandArgs: Array.isArray(row.command_args)
      ? row.command_args.map(String)
      : [],
    status: (["pending", "running", "completed", "failed", "stopped"].includes(
      String(row.status),
    )
      ? String(row.status)
      : "pending") as QueueJob["status"],
    progress: Number(row.progress) || 0,
    loss: row.loss != null ? Number(row.loss) : null,
    exitCode: row.exit_code != null ? Number(row.exit_code) : null,
    error: row.error != null ? String(row.error) : null,
    logs: Array.isArray(row.logs) ? row.logs.map(String) : [],
    createdAt:
      row.created_at instanceof Date
        ? row.created_at.toISOString()
        : String(row.created_at),
    startedAt:
      row.started_at != null
        ? row.started_at instanceof Date
          ? row.started_at.toISOString()
          : String(row.started_at)
        : null,
    finishedAt:
      row.finished_at != null
        ? row.finished_at instanceof Date
          ? row.finished_at.toISOString()
          : String(row.finished_at)
        : null,
  };
}

export { rowToQueueJob };

// ── Helpers ────────────────────────────────────────────────────────────────

function isoNow(): string {
  return new Date().toISOString();
}

function parseLoss(line: string): number | null {
  const match = line.match(/loss[:=]\s*([0-9]*\.?[0-9]+)/i);
  return match ? Number(match[1]) : null;
}

/**
 * Reads retry configuration and current retry count from a job's metadata column.
 */
async function readRetryConfig(
  jobId: string,
): Promise<{ retryCount: number; retryMax: number; retryDelayBaseMs: number }> {
  try {
    const rows = await query(
      `SELECT metadata FROM pipeline_jobs WHERE id = $1`,
      [jobId],
    );
    if (rows.length === 0) {
      return { retryCount: 0, retryMax: 3, retryDelayBaseMs: 5000 };
    }
    const meta = rows[0].metadata as Record<string, unknown> | null;
    return {
      retryCount:
        meta != null && typeof meta.retryCount === "number"
          ? meta.retryCount
          : 0,
      retryMax:
        meta != null && typeof meta.retryMax === "number"
          ? meta.retryMax
          : 3,
      retryDelayBaseMs:
        meta != null && typeof meta.retryDelayBaseMs === "number"
          ? meta.retryDelayBaseMs
          : 5000,
    };
  } catch {
    return { retryCount: 0, retryMax: 3, retryDelayBaseMs: 5000 };
  }
}

/**
 * Stores the child PID in the job's metadata column for restart recovery.
 */
async function storePid(jobId: string, pid: number): Promise<void> {
  if (!Number.isFinite(pid)) return;
  await query(
    `UPDATE pipeline_jobs
     SET metadata = jsonb_set(COALESCE(metadata, '{}'), '{pid}', $2::jsonb),
         updated_at = NOW()
     WHERE id = $1`,
    [jobId, JSON.stringify(pid)],
  );
}

/**
 * Appends a batch of log lines to the TEXT[] column.
 */
async function appendLogs(jobId: string, lines: string[]): Promise<void> {
  if (lines.length === 0) return;
  // Append all lines in a single query using array concatenation (||).
  await query(
    `UPDATE pipeline_jobs
     SET logs = COALESCE(logs, ARRAY[]::TEXT[]) || $2::TEXT[],
         updated_at = NOW()
     WHERE id = $1`,
    [jobId, lines],
  );
}

/**
 * Schedules a retry by setting status back to 'pending' with exponential
 * backoff in the metadata.nextRetryAt field.
 */
async function scheduleRetry(
  jobId: string,
  errorMessage: string,
  retryCount: number,
  retryMax: number,
  retryDelayBaseMs: number,
): Promise<void> {
  const backoffMs = retryDelayBaseMs * Math.pow(2, retryCount - 1);
  const nextRetryAt = new Date(Date.now() + backoffMs).toISOString();

  await query(
    `UPDATE pipeline_jobs
     SET status = 'pending',
         error = $2,
         metadata = jsonb_set(
           jsonb_set(
             jsonb_set(COALESCE(metadata, '{}'), '{retryCount}', $3::jsonb),
             '{nextRetryAt}',
             $4::jsonb
           ),
           '{retryMax}',
           $5::jsonb
         ),
         finished_at = NULL,
         updated_at = NOW()
     WHERE id = $1`,
    [
      jobId,
      errorMessage,
      JSON.stringify(retryCount),
      JSON.stringify(nextRetryAt),
      JSON.stringify(retryMax),
    ],
  );

  logger.info("Queue: job scheduled for retry", {
    jobId,
    retryCount,
    backoffMs,
    nextRetryAt,
  });
}

/**
 * Finalises a job record — sets status, exit code, error, loss, and finished_at.
 */
async function finalizeJob(
  jobId: string,
  status: QueueJob["status"],
  exitCode: number | null,
  error: string | null,
  loss: number | null,
  finishedAt: string,
): Promise<void> {
  await query(
    `UPDATE pipeline_jobs
     SET status = $2,
         exit_code = $3,
         error = $4,
         loss = COALESCE($5, loss),
         progress = CASE WHEN $2 IN ('completed','stopped') THEN 100 ELSE progress END,
         finished_at = $6,
         updated_at = $6
     WHERE id = $1`,
    [jobId, status, exitCode, error, loss, finishedAt],
  );
}

// ── Process Job ────────────────────────────────────────────────────────────

/**
 * Spawns and monitors a child process for a single queue job.
 *
 * Periodically flushes log lines to the database. Parses training loss from
 * stdout/stderr. On failure, schedules a retry with exponential backoff if
 * retryMax has not been exhausted.
 *
 * @param job        - The job record to execute.
 * @param pool       - pg Pool instance (unused directly — queries go through
 *                     `lib/db.ts`'s query helper; pool is accepted for future
 *                     transactional needs).
 * @param tracker    - Shared tracker that receives the child process reference
 *                     (used by JobQueue for cancellation).
 * @param onUpdate   - Optional callback fired on every meaningful job state
 *                     change (used for WebSocket broadcasts).
 */
export async function processJob(
  job: QueueJob,
  pool: pg.Pool,
  tracker: JobProcessTracker,
  onUpdate?: (job: QueueJob) => void,
): Promise<void> {
  const jobId = job.id;

  // ── Guard: no command to run ──────────────────────────────────────────
  if (!job.commandArgs || job.commandArgs.length === 0) {
    await finalizeJob(
      jobId,
      "failed",
      -1,
      "No command arguments provided",
      null,
      isoNow(),
    );
    tracker.terminal = true;
    onUpdate?.({
      ...job,
      status: "failed",
      error: "No command arguments provided",
      finishedAt: isoNow(),
    });
    return;
  }

  // ── Mark as running ──────────────────────────────────────────────────
  const startedAt = isoNow();
  await query(
    `UPDATE pipeline_jobs
     SET status = 'running', started_at = $2, updated_at = $2
     WHERE id = $1`,
    [jobId, startedAt],
  );

  onUpdate?.({
    ...job,
    status: "running",
    startedAt,
    exitCode: null,
    error: null,
    finishedAt: null,
  });

  logger.info("Queue: job started", {
    jobId,
    command: job.commandArgs.join(" "),
    npcKey: job.npcKey,
  });

  // ── Spawn child process ──────────────────────────────────────────────
  const [cmd, ...args] = job.commandArgs;
  const child = spawn(cmd, args, {
    cwd: process.env.UNSLOTH_CORE_ROOT || process.cwd(),
    shell: false,
    stdio: ["ignore", "pipe", "pipe"],
    env: { ...process.env, NODE_ENV: process.env.NODE_ENV || "development" },
  });

  tracker.process = child;
  void storePid(jobId, child.pid ?? 0);

  // ── Output handling ──────────────────────────────────────────────────
  let lineBuffer: string[] = [];
  let lineCount = 0;
  let latestLoss: number | null = null;

  async function flushLogs(): Promise<void> {
    if (lineBuffer.length === 0) return;
    const batch = lineBuffer;
    lineBuffer = [];
    await appendLogs(jobId, batch);
  }

  function handleOutput(chunk: Buffer, source: "stdout" | "stderr"): void {
    const lines = chunk
      .toString()
      .split("\n")
      .map((l) => l.replace(/\r$/, ""))
      .filter(Boolean);

    for (const rawLine of lines) {
      const prefixed = `[${source.toUpperCase()}] ${rawLine}`;
      lineBuffer.push(prefixed);
      lineCount += 1;

      const parsed = parseLoss(rawLine);
      if (parsed !== null) {
        latestLoss = parsed;
      }
    }
  }

  // ── Stream handlers ──────────────────────────────────────────────────
  const flushInterval = setInterval(() => {
    flushLogs().catch((err) => {
      logger.error("Queue: failed to flush logs", {
        jobId,
        error: err instanceof Error ? err.message : String(err),
      });
    });
  }, LOG_FLUSH_INTERVAL_MS);

  child.stdout.on("data", (chunk: Buffer) => handleOutput(chunk, "stdout"));
  child.stderr.on("data", (chunk: Buffer) => handleOutput(chunk, "stderr"));

  child.on("error", (err) => {
    logger.error("Queue: child process error", {
      jobId,
      error: err.message,
    });
  });

  // ── Process exit ─────────────────────────────────────────────────────
  const exitCode = await new Promise<number | null>((resolve) => {
    child.on("close", (code) => resolve(code ?? -1));
  });

  clearInterval(flushInterval);
  await flushLogs();

  // Flush loss to DB
  if (latestLoss !== null) {
    await query(
      `UPDATE pipeline_jobs SET loss = $2, updated_at = NOW() WHERE id = $1`,
      [jobId, latestLoss],
    );
  }

  // ── Determine final status ───────────────────────────────────────────
  const now = isoNow();
  let finalStatus: QueueJob["status"];
  let finalError: string | null = null;

  if (tracker.stopRequested) {
    finalStatus = "stopped";
    finalError = "Job cancelled by user";
  } else if (exitCode === 0) {
    finalStatus = "completed";
  } else {
    finalStatus = "failed";
    finalError = `Process exited with code ${exitCode}`;
  }

  // ── Retry logic (only for failures, not user-stopped) ────────────────
  if (finalStatus === "failed") {
    const retryCfg = await readRetryConfig(jobId);

    if (retryCfg.retryCount < retryCfg.retryMax) {
      const newRetryCount = retryCfg.retryCount + 1;
      await scheduleRetry(
        jobId,
        finalError ?? `Process exited with code ${exitCode}`,
        newRetryCount,
        retryCfg.retryMax,
        retryCfg.retryDelayBaseMs,
      );

      tracker.terminal = true;
      onUpdate?.({
        ...job,
        status: "pending",
        error: finalError,
        loss: latestLoss,
        exitCode,
        startedAt,
        finishedAt: null,
      });
      return;
    }
  }

  // ── Finalize (no retry, or retries exhausted) ────────────────────────
  await finalizeJob(jobId, finalStatus, exitCode, finalError, latestLoss, now);
  tracker.terminal = true;

  onUpdate?.({
    ...job,
    status: finalStatus,
    exitCode,
    error: finalError,
    loss: latestLoss,
    progress: finalStatus === "completed" || finalStatus === "stopped" ? 100 : job.progress,
    startedAt,
    finishedAt: now,
  });

  logger.info("Queue: job finished", {
    jobId,
    status: finalStatus,
    exitCode,
    loss: latestLoss,
  });
}
