import fs from "fs";
import path from "path";
import { query } from "./db";

const runtimeDir = path.join(process.cwd(), ".runtime");
const logsDir = path.join(runtimeDir, "logs");

/**
 * Read job logs, first trying the pipeline_jobs.logs column in the database.
 * Falls back to the per-job log file on disk.
 *
 * When the job runs via the queue worker, logs are written to the DB TEXT[]
 * column directly. When the job runs from CLI, the DB column is populated
 * by the WorkflowHookRecorder on step completion. This function resolves
 * from whichever source has data.
 *
 * Returns the last `maxLines` lines as a string array.
 */
export async function readJobLogs(
  jobId: string,
  maxLines = 200,
): Promise<string[]> {
  // ── Try DB first ─────────────────────────────────────────────────────
  try {
    const rows = await query<{ logs: string[] | null }>(
      "SELECT logs FROM pipeline_jobs WHERE id = $1",
      [jobId],
    );
    if (
      rows.length > 0 &&
      Array.isArray(rows[0].logs) &&
      rows[0].logs.length > 0
    ) {
      return rows[0].logs.slice(-maxLines);
    }
  } catch {
    // DB not available — fall through to filesystem
  }

  // ── Fallback to filesystem ───────────────────────────────────────────
  return readJobLogsFromFile(jobId, maxLines);
}

/**
 * Read job logs from the per-job log file on disk.
 * Returns the last `maxLines` lines.
 */
export function readJobLogsFromFile(jobId: string, maxLines = 200): string[] {
  try {
    const logPath = path.join(logsDir, jobId + ".log");
    if (!fs.existsSync(logPath)) return [];
    return fs
      .readFileSync(logPath, "utf8")
      .split("\n")
      .filter(Boolean)
      .slice(-maxLines);
  } catch {
    return [];
  }
}

/**
 * Write a line to the per-job log file.
 */
export function writeJobLog(jobId: string, line: string): void {
  try {
    fs.mkdirSync(logsDir, { recursive: true });
    const logPath = path.join(logsDir, jobId + ".log");
    const entry = `[${new Date().toISOString()}] ${line}\n`;
    fs.appendFileSync(logPath, entry, "utf8");
  } catch {
    /* best-effort */
  }
}
