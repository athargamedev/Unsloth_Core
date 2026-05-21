// --- Types ---

export interface Stage {
  name: string;
  status: 'completed' | 'running' | 'pending' | 'failed' | 'stopped';
  logs: string[];
}

export interface Job {
  id: string;
  name: string;
  status: 'running' | 'completed' | 'pending' | 'stopped' | 'failed';
  progress: number;
  loss: number | null;
  type: string;
  commandId?: string;
  createdAt: string;
  stages: Stage[];
  command?: string[];
  startedAt?: string;
  finishedAt?: string;
  logs?: string[];
  npcKey?: string;
  wandbUrl?: string | null;
}

export interface JobsSnapshot {
  jobs: Job[];
  workflowCount: number;
  autoSyncExternal: boolean;
}

export interface WatchAlert {
  timestamp: string;
  line: string;
  command: string;
}

export interface WatchRunSummary {
  watchDir: string;
  startedAt: string | null;
  finishedAt: string | null;
  returncode: number | null;
  command: string[];
  alerts: WatchAlert[];
  alertCount: number;
  streamTail: string[];
}

export interface WatchLogsSnapshot {
  root: string;
  totalAlerts: number;
  latestRun: WatchRunSummary | null;
  runs: WatchRunSummary[];
}

export interface DatasetVersion {
  tag: string;
  size: string;
  entries: number;
  createdAt: string;
}

export interface Dataset {
  id: string;
  name: string;
  versions: DatasetVersion[];
}

export interface Subject {
  id: string;
  path: string;
}

export interface AvailableCommand {
  id: string;
  label: string;
  icon: string;
  color: 'accent' | 'success' | 'warning' | 'danger' | 'default';
  type: string;
  requiredFields: string[];
}

export interface AssistantMessage {
  role: 'user' | 'assistant';
  content: string;
}

export interface SystemStatus {
  executionMode: 'local' | 'remote';
  runningJobs: number;
  totalJobs: number;
  repoRoot?: string;
  timestamp: string;
  localModel: LocalModelStatus;
}

export interface LocalModelStatus {
  loaded: boolean;
  source: 'llama-server' | 'ollama' | 'export' | 'job' | 'none';
  displayName: string | null;
  modelId?: string | null;
  ggufPath?: string | null;
  npcKey?: string | null;
  pid?: number | null;
  port?: number | null;
  updatedAt: string;
}

export interface HealthCheck {
  ok: boolean;
  checks: Record<string, boolean>;
  executionMode: 'local' | 'remote';
  runningJobs: number;
  processId: number;
  timestamp: string;
}

export interface Telemetry {
  gpuName: string;
  gpuLoad: number;
  gpuTemperature: number;
  gpuMemoryUsedGB: number;
  gpuMemoryTotalGB: number;
  cpuLoad: number;
  memoryUsedGB: number;
  memoryTotalGB: number;
  networkRxMBps: number;
  networkTxMBps: number;
  platform: string;
  nodeVersion: string;
  nodeId: string;
  timestamp: string;
}

export interface RunArtifact {
  id: string;
  npcKey: string;
  runId?: string;
  path?: string;
  layout?: 'canonical' | 'legacy';
  updatedAt: string;
  model?: string | null;
  datasetPath?: string | null;
  technique?: string | null;
  loss?: number | null;
  trainRuntime?: number | null;
  trainSamplesPerSecond?: number | null;
  trainStepsPerSecond?: number | null;
  epoch?: number | null;
  batchSize?: number | null;
  epochs?: number | null;
  learningRate?: number | null;
  loraRank?: number | null;
  loraAlpha?: number | null;
  wandbEnabled?: boolean | null;
  hasConfigSnapshot?: boolean;
  hasAdapter?: boolean;
  hasTensorBoard?: boolean;
}

export interface ExportArtifact {
  npcKey: string;
  file: string;
  updatedAt: string;
}

export interface TrainingConfig {
  spec: string;
  preset: string;
  technique: string;
  baseModel: string;
  learningRate: string;
  scheduler: 'cosine' | 'linear' | 'constant';
  batchSize: number;
  epochs: number;
  rank: number;
  alpha: number;
  wandb?: boolean;
}

export interface CommandPayload {
  commandId: string;
  type: string;
  [key: string]: unknown;
}

export interface TensorBoardScalar {
  step: number;
  value: number;
}

export interface TensorBoardData {
  runId: string;
  scalars: Record<string, TensorBoardScalar[]>;
  error?: string | null;
}

export interface WsMessage {
  type: 'telemetry' | 'job_update' | 'status';
  payload: any;
  timestamp: string;
}

export interface DatasetSample {
  messages?: Array<{ role: string; content: string }>;
  _parseError?: boolean;
  _raw?: string;
  [key: string]: unknown;
}

export interface DatasetContent {
  npcKey: string;
  technique: string;
  total: number;
  samples: DatasetSample[];
  showing: number;
}

export interface EvalReportFile {
  name: string;
  path: string;
}

export interface EvalReportGroup {
  npcKey: string;
  files: EvalReportFile[];
}

export interface EvalReportsData {
  reports: EvalReportGroup[];
  comparisons: EvalReportFile[];
}

export interface RunDetail {
  npcKey: string;
  runId: string;
  path: string;
  config: Record<string, unknown>;
  metrics: Record<string, unknown>;
}

// --- Pipeline State types ---

export interface PipelineNpcState {
  status: string;
  weak_concepts_count?: number;
  focus_categories?: string[];
  knowledge_gaps?: number;
  training_density_issues?: number;
  latest_gguf?: string;
  latest_win_rate?: number;
  auto_retrain_complete?: boolean;
  last_updated?: string;
  dataset?: string;
  training?: string;
  gguf_adapter?: string;
  eval_report?: string;
  gguf_validation?: string;
  [key: string]: unknown;
}

export type PipelineState = Record<string, PipelineNpcState>;

export interface PipelineRunRecord {
  ts?: string;
  event?: string;
  run_id?: string;
  npc_key?: string;
  stage?: string;
  technique?: string | null;
  spec_path?: string | null;
  preset?: string | null;
  entrypoint?: string | null;
  frontend_job_id?: string | null;
  pid?: number | null;
  run_dir?: string | null;
  status?: string | null;
  error?: string | null;
  message?: string | null;
  artifacts?: Record<string, unknown>;
  metrics?: Record<string, unknown>;
  [key: string]: unknown;
}

export interface PipelineRunsResponse {
  runs: PipelineRunRecord[];
  total_events: number;
}

export interface PipelineRunDetail {
  run: Record<string, unknown>;
  events: PipelineRunRecord[];
  hooks: unknown[];
  log: string[];
}

// --- Feedback types ---

export interface ConceptFeedback {
  total: number;
  baseline_wins: number;
  candidate_wins: number;
  ties: number;
  win_rate: number;
  avg_baseline_quality: number;
  avg_candidate_quality: number;
  constraint_violations: number;
  examples?: Array<{
    question: string;
    winner: string;
    candidate_quality?: number;
    candidate_words?: number;
    [key: string]: unknown;
  }>;
}

export interface FeedbackResult {
  npc_key: string;
  baseline: string;
  candidate: string;
  total_examples: number;
  baseline_wins: number;
  candidate_wins: number;
  ties: number;
  win_rate: number;
  per_concept: Record<string, ConceptFeedback>;
  weak_concepts: string[];
  timestamp: string;
  gaps?: FeedbackGapResult[];
}

export interface FeedbackGapResult {
  concept: string;
  category: string;
  gap_type: 'training_density' | 'knowledge_gap';
  onyx_result_count: number;
  onyx_sources?: string[];
}

// --- Supabase types ---

export interface SupabaseTestResult {
  id: string;
  npc_id: string;
  test_name: string;
  test_type: string;
  score: number;
  metrics: Record<string, number>;
  created_at: string;
}

export interface SupabaseNpcProfile {
  npc_id: string;
  npc_name: string;
  display_name: string;
  description: string;
  is_active: boolean;
  lora_path: string;
  lora_weight: number;
  created_at: string;
}

export interface SupabaseLeaderboardEntry {
  rank: number;
  npc_id: string;
  npc_name: string;
  test_name: string;
  score: number;
  metrics: Record<string, number>;
}

export interface SupabaseStatus {
  connected: boolean;
  url: string;
  error?: string;
}

// --- Manifest types ---

export interface ManifestInfo {
  name: string;
  path: string;
  manifest_name: string;
  description: string;
  version: string;
  source_count: number;
  total_questions: number;
  lastModified: string;
}

export interface ManifestSource {
  path: string;
  kind?: string;
  section_hints?: string[];
  questions?: Array<{
    prompt: string;
    category?: string;
    max_sentences?: number;
    include_commands?: boolean;
  }>;
  exists?: boolean;
  doc_size?: string;
}

export interface ManifestDetail {
  manifest_name: string;
  description: string;
  version: string;
  sources: ManifestSource[];
  manifest_path: string;
}

// --- Dataset Quality types ---

export interface QualityMetric {
  count: number;
  average_score: number;
  pass_rate: number;
}

export interface QualityCategory {
  total: number;
  passed: number;
  pass_rate: number;
}

export interface QualitySummary {
  created_at: string;
  npc_key: string;
  technique: string;
  judge_model: string;
  total: number;
  passed: number;
  failed: number;
  pass_rate: number;
  metrics: Record<string, QualityMetric>;
  categories: Record<string, QualityCategory>;
  failures_path?: string;
}

export interface QualityFailureMetric {
  name: string;
  score: number;
  threshold: number;
  success: boolean;
  reason: string;
  evaluation_model: string;
  error?: string;
}

export interface QualityFailure {
  test_name: string;
  input: string;
  actual_output: string;
  metadata?: Record<string, unknown>;
  metric: QualityFailureMetric;
}

// --- API helpers ---

export const fetchJson = async <T,>(url: string): Promise<T> => {
  const response = await fetch(url);
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.error || `Request failed: ${url}`);
  }
  return response.json() as Promise<T>;
};

// --- Ollama Tuning types ---

export interface OllamaConfig {
  OLLAMA_NUM_PARALLEL: string;
  OLLAMA_FLASH_ATTENTION: string;
  OLLAMA_KV_CACHE_TYPE: string;
  num_gpu: string;
}

export interface OllamaStatus {
  running: boolean;
  pid?: number;
  config: OllamaConfig;
  activeModel: string | null;
  gpuLayers: number | null;
}

export interface OllamaModelInfo {
  name: string;
  size: string;
  modified: string;
  details?: {
    parameter_size?: string;
    quantization_level?: string;
    family?: string;
  };
}

export interface OllamaModelList {
  models: OllamaModelInfo[];
}

export interface OllamaApplyConfigPayload {
  OLLAMA_NUM_PARALLEL?: number;
  OLLAMA_FLASH_ATTENTION?: boolean;
  OLLAMA_KV_CACHE_TYPE?: string;
  num_gpu?: number;
  restart?: boolean;
}

export interface OllamaApplyResult {
  success: boolean;
  needsRestart: boolean;
  message: string;
}

export const fetchOptionalJson = async <T,>(url: string): Promise<T | null> => {
  try {
    return await fetchJson<T>(url);
  } catch {
    return null;
  }
};
