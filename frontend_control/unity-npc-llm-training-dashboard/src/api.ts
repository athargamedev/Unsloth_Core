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
  createdAt: string;
  stages: Stage[];
  command?: string[];
  startedAt?: string;
  finishedAt?: string;
  logs?: string[];
  npcKey?: string;
  wandbUrl?: string | null;
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
  updatedAt: string;
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

// --- API helpers ---

export const fetchJson = async <T,>(url: string): Promise<T> => {
  const response = await fetch(url);
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.error || `Request failed: ${url}`);
  }
  return response.json() as Promise<T>;
};

export const fetchOptionalJson = async <T,>(url: string): Promise<T | null> => {
  try {
    return await fetchJson<T>(url);
  } catch {
    return null;
  }
};
