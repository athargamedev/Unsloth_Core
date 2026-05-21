import fs from "fs";
import path from "path";
import os from "os";

const runtimeDir = path.join(process.cwd(), ".runtime");
const logsDir = path.join(runtimeDir, "logs");

/**
 * Read job logs from the per-job log file.
 * Returns the last `maxLines` lines.
 */
export function readJobLogs(jobId: string, maxLines = 200): string[] {
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
