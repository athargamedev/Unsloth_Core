import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  fetchJson,
  fetchOptionalJson,
  type Job,
  type JobsSnapshot,
  type Telemetry,
  type SystemStatus,
  type HealthCheck,
  type Dataset,
  type Subject,
  type RunArtifact,
  type ExportArtifact,
  type WatchLogsSnapshot,
  type OllamaStatus,
  type OllamaModelList,
  type PipelineState,
  type PipelineRunsResponse,
  type QualitySummary,
  type QualityFailure,
  type EvalReportsData,
  type FeedbackFileInfo,
  type TensorBoardData,
  type PipelineRunDetail,
} from '../api';

// ============================================================
// Query Key Factory
// ============================================================

export const queryKeys = {
  jobs: {
    all: ['jobs'] as const,
    list: (filters?: Record<string, string>) => ['jobs', 'list', filters] as const,
    detail: (id: string) => ['jobs', 'detail', id] as const,
    state: ['jobs', 'state'] as const,
    watchLogs: ['jobs', 'watchLogs'] as const,
  },
  telemetry: ['telemetry'] as const,
  system: {
    status: ['system', 'status'] as const,
    health: ['system', 'health'] as const,
  },
  datasets: {
    all: ['datasets'] as const,
    detail: (npcKey: string, technique: string) => ['datasets', npcKey, technique] as const,
  },
  subjects: ['subjects'] as const,
  runs: ['runs'] as const,
  exports: ['exports'] as const,
  presets: ['presets'] as const,
  quality: {
    summary: (npcKey?: string, technique?: string) => ['quality', npcKey, technique] as const,
    failures: (npcKey?: string, technique?: string) => ['quality', 'failures', npcKey, technique] as const,
  },
  pipeline: {
    state: ['pipeline', 'state'] as const,
    npcStatus: (npcKey: string) => ['pipeline', 'npc', npcKey] as const,
    runs: (npcKey?: string, limit?: number) => ['pipeline', 'runs', npcKey, limit] as const,
  },
  evalReports: ['eval-reports'] as const,
  feedbackResults: ['feedback-results'] as const,
  tensorboard: (npcKey: string, runId: string) => ['tensorboard', npcKey, runId] as const,
  ollama: {
    status: ['ollama', 'status'] as const,
    models: ['ollama', 'models'] as const,
  },
  supabase: {
    status: ['supabase', 'status'] as const,
    leaderboard: ['supabase', 'leaderboard'] as const,
  },
  logs: ['logs'] as const,
};

// ============================================================
// Queries
// ============================================================

/**
 * Full job state snapshot (jobs list + workflow metadata).
 * Polls every 5 s, considers data fresh for 3 s.
 */
export function useJobsQuery() {
  return useQuery({
    queryKey: queryKeys.jobs.state,
    queryFn: () => fetchJson<JobsSnapshot>('/api/jobs/state'),
    refetchInterval: 5000,
    staleTime: 3000,
  });
}

/**
 * Watch-logs snapshot (filesystem alert data).
 * Polls every 10 s — less latency-sensitive than job state.
 */
export function useWatchLogsQuery() {
  return useQuery({
    queryKey: queryKeys.jobs.watchLogs,
    queryFn: () =>
      fetchJson<WatchLogsSnapshot>('/api/watch-logs').catch(() => null),
    refetchInterval: 10_000,
    staleTime: 5000,
  });
}

/**
 * GPU / CPU telemetry.
 * Polls faster (3 s) because telemetry is the most latency-sensitive data.
 */
export function useTelemetryQuery() {
  return useQuery({
    queryKey: queryKeys.telemetry,
    queryFn: () => fetchJson<Telemetry>('/api/telemetry'),
    refetchInterval: 3000,
    staleTime: 2000,
  });
}

/**
 * System execution mode & local model status.
 */
export function useSystemStatusQuery() {
  return useQuery({
    queryKey: queryKeys.system.status,
    queryFn: () => fetchJson<SystemStatus>('/api/system/status'),
    refetchInterval: 5000,
    staleTime: 3000,
  });
}

/**
 * Health-check endpoint (lightweight, mostly for the footer status bar).
 */
export function useHealthQuery() {
  return useQuery({
    queryKey: queryKeys.system.health,
    queryFn: () => fetchJson<HealthCheck>('/api/health').catch(() => null),
    refetchInterval: 10_000,
    staleTime: 5000,
  });
}

/**
 * Dataset catalog.  Changes less frequently so we use a longer stale time
 * and no polling interval.
 */
export function useDatasetsQuery() {
  return useQuery({
    queryKey: queryKeys.datasets.all,
    queryFn: () => fetchJson<Dataset[]>('/api/datasets'),
    staleTime: 10_000,
  });
}

/**
 * NPC subject list.  Almost never changes during a session.
 */
export function useSubjectsQuery() {
  return useQuery({
    queryKey: queryKeys.subjects,
    queryFn: () => fetchJson<Subject[]>('/api/subjects'),
    staleTime: 30_000,
  });
}

/**
 * Training run artifacts.
 */
export function useRunsQuery() {
  return useQuery({
    queryKey: queryKeys.runs,
    queryFn: () => fetchJson<RunArtifact[]>('/api/runs'),
    staleTime: 10_000,
  });
}

/**
 * GGUF export artifacts.
 */
export function useExportsQuery() {
  return useQuery({
    queryKey: queryKeys.exports,
    queryFn: () => fetchJson<ExportArtifact[]>('/api/exports'),
    staleTime: 10_000,
  });
}

/**
 * Training presets — change very rarely.
 */
export function usePresetsQuery() {
  return useQuery({
    queryKey: queryKeys.presets,
    queryFn: () =>
      fetchJson<Array<{ name: string; description: string }>>('/api/presets').catch(() =>
        fetchJson<Array<{ name: string; description: string }>>('/api/config/presets'),
      ),
    staleTime: 60_000,
  });
}

/**
 * Server-side console log buffer.
 */
export function useLogsQuery() {
  return useQuery({
    queryKey: queryKeys.logs,
    queryFn: () => fetchJson<string[]>('/api/logs'),
    refetchInterval: 5000,
    staleTime: 3000,
  });
}

// ============================================================
// Ollama Queries
// ============================================================

/**
 * Ollama service status (running, config, active model).
 */
export function useOllamaStatusQuery() {
  return useQuery({
    queryKey: queryKeys.ollama.status,
    queryFn: () => fetchJson<OllamaStatus>('/api/ollama/status'),
    staleTime: 10_000,
    retry: 2,
  });
}

/**
 * Ollama model inventory list.
 */
export function useOllamaModelsQuery() {
  return useQuery({
    queryKey: queryKeys.ollama.models,
    queryFn: () => fetchJson<OllamaModelList>('/api/ollama/models'),
    staleTime: 30_000,
    retry: 2,
  });
}

// ============================================================
// Pipeline Queries
// ============================================================

/**
 * Full pipeline state for all NPCs.
 * Polls every 15 s.
 */
export function usePipelineStateQuery() {
  return useQuery({
    queryKey: queryKeys.pipeline.state,
    queryFn: () =>
      fetchJson<PipelineState>('/api/pipeline-state').catch(() => ({} as PipelineState)),
    refetchInterval: 15_000,
    staleTime: 10_000,
  });
}

/**
 * Pipeline run detail for a specific run ID.
 */
export function usePipelineRunDetailQuery(runId: string | null) {
  return useQuery({
    queryKey: ['pipeline', 'run-detail', runId],
    queryFn: () =>
      fetchJson<PipelineRunDetail>(`/api/pipeline/runs/${encodeURIComponent(runId ?? '')}`),
    staleTime: 10_000,
    enabled: !!runId,
  });
}

/**
 * Pipeline run history.
 */
export function usePipelineRunsQuery(npcKey?: string, limit = 24) {
  return useQuery({
    queryKey: queryKeys.pipeline.runs(npcKey, limit),
    queryFn: () =>
      fetchJson<PipelineRunsResponse>(`/api/pipeline/runs?limit=${limit}${npcKey ? `&npcKey=${encodeURIComponent(npcKey)}` : ''}`),
    refetchInterval: 15_000,
    staleTime: 10_000,
    retry: 2,
  });
}

// ============================================================
// Dataset Quality Queries
// ============================================================

/**
 * Quality summary for a specific NPC technique dataset.
 * Pass `enabled = false` to defer loading until a condition is met.
 */
export function useQualitySummaryQuery(npcKey: string, technique: string, enabled = true) {
  return useQuery({
    queryKey: [...queryKeys.quality.summary(npcKey, technique)],
    queryFn: () => fetchOptionalJson<QualitySummary>(`/api/datasets/quality-summary/${npcKey}/${technique}`),
    staleTime: 30_000,
    enabled: enabled && !!npcKey && !!technique,
  });
}

/**
 * Quality failures for a specific NPC technique dataset.
 */
export function useQualityFailuresQuery(npcKey: string, technique: string, enabled = true) {
  return useQuery({
    queryKey: [...queryKeys.quality.failures(npcKey, technique)],
    queryFn: () =>
      fetchOptionalJson<QualityFailure[]>(`/api/datasets/quality-failures/${npcKey}/${technique}`),
    staleTime: 30_000,
    enabled: enabled && !!npcKey && !!technique,
  });
}

// ============================================================
// Eval & Feedback Queries
// ============================================================

/**
 * Eval reports index (HTML report files per NPC).
 */
export function useEvalReportsQuery() {
  return useQuery({
    queryKey: queryKeys.evalReports,
    queryFn: () => fetchOptionalJson<EvalReportsData>('/api/eval-reports'),
    staleTime: 15_000,
  });
}

/**
 * Feedback results file list.
 */
export function useFeedbackResultsQuery() {
  return useQuery({
    queryKey: queryKeys.feedbackResults,
    queryFn: () => fetchJson<FeedbackFileInfo[]>('/api/feedback-results').catch(() => [] as FeedbackFileInfo[]),
    staleTime: 15_000,
  });
}

// ============================================================
// TensorBoard Queries
// ============================================================

/**
 * TensorBoard scalar data for a given NPC run.
 */
export function useTensorBoardQuery(npcKey: string, runId: string) {
  return useQuery({
    queryKey: queryKeys.tensorboard(npcKey, runId),
    queryFn: () =>
      fetchJson<TensorBoardData>(
        `/api/tensorboard?npcKey=${encodeURIComponent(npcKey)}&runId=${encodeURIComponent(runId)}`,
      ),
    staleTime: 60_000,
    enabled: !!npcKey && !!runId,
  });
}

// ============================================================
// Convenience: list of all active queries for a unified refresh
// ============================================================

export const ALL_QUERY_KEYS: readonly (readonly unknown[])[] = [
  queryKeys.jobs.state,
  queryKeys.jobs.watchLogs,
  queryKeys.telemetry,
  queryKeys.system.status,
  queryKeys.system.health,
  queryKeys.datasets.all,
  queryKeys.subjects,
  queryKeys.runs,
  queryKeys.exports,
  queryKeys.presets,
  queryKeys.logs,
  queryKeys.ollama.status,
  queryKeys.ollama.models,
  queryKeys.pipeline.state,
  queryKeys.evalReports,
  queryKeys.feedbackResults,
];

// ============================================================
// Mutations
// ============================================================

/** Start a new pipeline command / job. */
export function useStartJobMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: Record<string, unknown>) =>
      fetch('/api/commands/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      }).then((r) => {
        if (!r.ok) return r.json().then((e) => Promise.reject(new Error(e.error || 'Failed to start job')));
        return r.json();
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.jobs.all });
    },
  });
}

/** Stop a running job by ID. */
export function useStopJobMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (jobId: string) =>
      fetch('/api/commands/stop', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: jobId }),
      }).then((r) => {
        if (!r.ok) return r.json().then((e) => Promise.reject(new Error(e.error || 'Failed to stop job')));
        return r.json();
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.jobs.all });
    },
  });
}

/** Delete / dismiss a single job record. */
export function useDeleteJobMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (jobId: string) =>
      fetch(`/api/jobs/${jobId}`, { method: 'DELETE' }).then((r) => {
        if (!r.ok) return r.json().then((e) => Promise.reject(new Error(e.error || 'Failed to delete job')));
        return r.json();
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.jobs.all });
    },
  });
}

/** Clear the entire job registry. */
export function useClearJobsMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () =>
      fetch('/api/jobs/clear', { method: 'POST' }).then((r) => {
        if (!r.ok) return r.json().then((e) => Promise.reject(new Error(e.error || 'Failed to clear jobs')));
        return r.json();
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.jobs.all });
    },
  });
}

/** Sync job registry with filesystem watch. */
export function useSyncJobsMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (force: boolean) =>
      fetch('/api/jobs/sync', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ force }),
      }).then((r) => {
        if (!r.ok) return r.json().then((e) => Promise.reject(new Error(e.error || 'Failed to sync jobs')));
        return r.json();
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.jobs.all });
    },
  });
}

/** Clear server-side log buffer. */
export function useClearLogsMutation() {
  return useMutation({
    mutationFn: () =>
      fetch('/api/logs/clear', { method: 'POST' }).then((r) => {
        if (!r.ok) return r.json().then((e) => Promise.reject(new Error(e.error || 'Failed to clear logs')));
        return r.json();
      }),
  });
}
