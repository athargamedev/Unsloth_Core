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
  timestamp: string;
}

export interface HealthCheck {
  ok: boolean;
  checks: Record<string, boolean>;
  executionMode: 'local' | 'remote';
  runningJobs: number;
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
  baseModel: string;
  learningRate: string;
  batchSize: number;
  epochs: number;
  rank: number;
  alpha: number;
}

export interface CommandPayload {
  commandId: string;
  type: string;
  [key: string]: unknown;
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
