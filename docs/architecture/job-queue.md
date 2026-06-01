# PostgreSQL-Backed Job Queue

## Overview

The job queue (`src/backend/services/job-queue.ts`) is a lightweight, PostgreSQL-backed queue for the Unsloth_Core pipeline. No Redis required. It uses `FOR UPDATE SKIP LOCKED` polling to pick up pending jobs and manages process lifecycle with PID tracking and exponential backoff retry.

Designed as a drop-in conceptual replacement for BullMQ when Redis is unavailable.

## How It Works

### 1. Job Insertion

A job is enqueued by inserting a row into the `pipeline_jobs` table with status `pending`:

```typescript
const job = await jobQueue.enqueue(
  "history_guide",     // npcKey
  "Training",          // type
  "train",             // commandId
  ["--preset", "fast-3b"]  // commandArgs
);
```

### 2. Polling Loop

A `setInterval` timer runs every **2 seconds** (configurable via `pollIntervalMs`) and executes:

```sql
SELECT * FROM pipeline_jobs
WHERE status = 'pending'
  AND (metadata->>'nextRetryAt' IS NULL
       OR metadata->>'nextRetryAt' = 'null'
       OR (metadata->>'nextRetryAt')::TIMESTAMPTZ <= NOW())
ORDER BY created_at ASC
LIMIT $1
FOR UPDATE SKIP LOCKED
```

`FOR UPDATE SKIP LOCKED` ensures multiple queue instances don't fight over the same jobs — each picks up only unlocked pending rows.

### 3. Process Spawning

The poller spawns a child process for each claimed job:

```
pipeline_jobs row → spawn(command, args) → PID stored in metadata
```

The process is tracked in a `Map<jobId, {process, stopRequested, terminal}>`.

### 4. Completion

On process exit:
- Exit code 0: status → `completed`
- Non-zero exit: status → `failed` (or retry if retries remain)
- Logs are flushed to the `logs` TEXT[] column incrementally

### 5. Retry with Exponential Backoff

Failed jobs are retried with exponential backoff: `2^n * retryDelayBaseMs` (default: 5s base, so 5s, 10s, 20s, 40s, 80s). The `nextRetryAt` timestamp in `metadata` prevents the poller from picking up a job before its backoff period elapses. Maximum retry count: 3 (configurable via `retryMax`).

## Queue State Machine

```
pending → running → completed
                 → failed → pending (retry)
                 → stopped
paused  → running
```

Valid statuses: `pending`, `running`, `completed`, `failed`, `stopped`, `paused`.

## API

### Public Methods

| Method | Description |
|--------|-------------|
| `init()` | Ensures `pipeline_jobs` table exists (idempotent) |
| `enqueue(npcKey, type, commandId, commandArgs)` | Insert a new pending job |
| `start()` | Begin polling loop, recover running jobs |
| `stop(timeoutMs)` | Graceful shutdown (SIGTERM → 30s → SIGKILL) |
| `cancel(jobId)` | Cancel a running job (SIGTERM → 10s → SIGKILL) |
| `retry(jobId)` | Reset a failed/stopped job to pending |
| `getJob(jobId)` | Fetch a single job |
| `listJobs(filters)` | List jobs with optional npcKey/status/limit/offset |
| `getStats()` | Return cached queue statistics |
| `clean(maxAgeDays)` | Archive terminal jobs older than N days |
| `onUpdate(callback)` | Register callback for job state changes |

### Queue Options

```typescript
interface QueueOptions {
  concurrency: 2,         // Max concurrent processes
  pollIntervalMs: 2000,   // Poll loop interval
  retryMax: 3,            // Max retry attempts
  retryDelayBaseMs: 5000, // Base backoff delay
  dbUrl?: string,         // Optional custom DB connection
}
```

## Process Lifecycle

### Cancel Flow

1. Client calls `cancel(jobId)`
2. SIGTERM sent to process group (negative PID), then to process directly
3. If process doesn't exit within **STOP_ESCALATION_MS (10s)**, SIGKILL is sent
4. DB updated to `stopped` with exit code -15 (SIGTERM) or -9 (SIGKILL)

### Graceful Shutdown Flow

1. `stop(timeoutMs)` called (default 30s wait, 10s force)
2. Polling stopped
3. Wait for running jobs to complete or timeout
4. SIGTERM → wait 2s → SIGKILL for remaining jobs
5. All DB entries updated to `stopped` with message "Server shutdown — job terminated"

## Server Restart Recovery

On startup, `recoverRunningJobs()` queries all jobs with status `running`:

- **PID alive** (checked via `process.kill(pid, 0)`): Job marked as recovered, continues monitoring
- **PID dead** (server restart lost the process): Job marked as `failed` with message "Server restarted — job lost (PID X not found)"

A periodic health check (`checkRecoveredProcessHealth`, every 10s) monitors recovered processes for unexpected death.

## Stats and Performance

Instead of full-table aggregate scans on every poll cycle, stats are updated **incrementally** on each job state transition:

```typescript
cachedStats = { pending, running, completed, failed, stopped, total, activeWorkers }
```

A **full recount** is triggered every 50 transitions as a safety check against drift.

## Concurrency

Configurable max concurrent jobs (default: 2 for the RTX 3060 6GB). The poller checks `this.runningJobs.size >= this.options.concurrency` before claiming new jobs.

## WebSocket Integration

The `onUpdate(callback)` fires on every job state change. This is used to broadcast job updates to connected WebSocket clients:

```typescript
jobQueue.onUpdate((job) => {
  broadcast("job_update", job);
});
```

## Comparison: BullMQ vs JobQueue

| Feature | BullMQ (Redis) | JobQueue (PostgreSQL) |
|---------|---------------|----------------------|
| Dependency | Redis required | No extra service |
| Persistence | Redis AOF/RDB | PostgreSQL ACID |
| Polling | Push-based (blocking pop) | Pull-based (SKIP LOCKED, 2s interval) |
| Retry | Built-in | Metadata-based exponential backoff |
| Concurrency | Worker concurrency | Poller limit + process tracking |
| Priority | Queue priority | ORDER BY created_at ASC (FIFO) |

To swap to BullMQ, replace `JobQueue` with BullMQ's `Queue/Worker` — the `QueueJob` interface and `onUpdate` pattern are intentionally API-compatible.
