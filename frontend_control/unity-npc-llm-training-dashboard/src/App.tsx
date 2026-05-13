import { useState, useEffect } from 'react';
import { 
  Play, 
  Square, 
  Terminal, 
  BarChart3, 
  MessageSquare, 
  Settings, 
  Database, 
  Shield, 
  Sparkles,
  Zap,
  Activity,
  Cpu,
  Layers,
  ChevronRight,
  Search,
  Bell,
  User,
  ExternalLink,
  XCircle,
} from 'lucide-react';
import { motion, AnimatePresence } from 'motion/react';
import { cn } from './lib/utils';
import { 
  LineChart, 
  Line, 
  XAxis, 
  YAxis, 
  CartesianGrid, 
  Tooltip, 
  ResponsiveContainer,
  AreaChart,
  Area
} from 'recharts';

// --- Types ---
interface Stage {
  name: string;
  status: 'completed' | 'running' | 'pending' | 'failed';
  logs: string[];
}

interface Job {
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

interface DatasetVersion {
  tag: string;
  size: string;
  entries: number;
  createdAt: string;
}

interface Dataset {
  id: string;
  name: string;
  versions: DatasetVersion[];
}

interface Subject {
  id: string;
  path: string;
}

interface AvailableCommand {
  id: string;
  label: string;
  icon: string;
  color: 'accent' | 'success' | 'warning' | 'danger' | 'default';
  type: string;
  requiredFields: string[];
}

interface AssistantMessage {
  role: 'user' | 'assistant';
  content: string;
}

interface SystemStatus {
  executionMode: 'local' | 'remote';
  runningJobs: number;
  totalJobs: number;
  timestamp: string;
}

interface HealthCheck {
  ok: boolean;
  checks: Record<string, boolean>;
  executionMode: 'local' | 'remote';
  runningJobs: number;
  timestamp: string;
}

interface Telemetry {
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

interface RunArtifact {
  id: string;
  npcKey: string;
  updatedAt: string;
}

interface ExportArtifact {
  npcKey: string;
  file: string;
  updatedAt: string;
}

// --- Components ---

const WorkflowVisualizer = ({ stages }: { stages: Stage[] }) => (
  <div className="flex items-center w-full gap-2 p-2">
    {stages.map((stage, i) => (
      <div key={i} className="flex-1 flex flex-col gap-2 relative">
        <div className="flex items-center gap-2">
          <div className={cn(
            "w-2.5 h-2.5 rounded-full z-10",
            stage.status === 'completed' ? "bg-success glow-blue" : 
            stage.status === 'running' ? "bg-warning animate-pulse" :
            stage.status === 'failed' ? "bg-danger ring-2 ring-danger/40" : "bg-line"
          )} />
          <span className={cn(
            "text-[9px] font-bold uppercase tracking-widest truncate",
            stage.status === 'running' ? "text-warning" :
            stage.status === 'completed' ? "text-ink" :
            stage.status === 'failed' ? "text-danger" : "text-ink/30"
          )}>
            {stage.name}
          </span>
        </div>
        {i < stages.length - 1 && (
          <div className={cn(
            "absolute left-1 top-[5px] h-[1px] w-[calc(100%+8px)] -z-0",
            stages[i+1].status === 'failed' ? "bg-danger" : stages[i+1].status !== 'pending' ? "bg-accent" : "bg-line"
          )} />
        )}
      </div>
    ))}
  </div>
);

const SidebarItem = ({ icon: Icon, label, active, onClick }: { icon: any, label: string, active?: boolean, onClick: () => void }) => (
  <button 
    onClick={onClick}
    className={cn(
      "w-full flex items-center gap-3 px-4 py-3 rounded-lg transition-all duration-200 group text-sm",
      active 
        ? "bg-accent/10 text-accent border border-accent/20" 
        : "text-ink/60 hover:text-ink hover:bg-surface"
    )}
  >
    <Icon className={cn("w-4 h-4 transition-transform group-hover:scale-110", active ? "text-accent" : "text-ink/40")} />
    <span className="font-medium">{label}</span>
    {active && <motion.div layoutId="sidebar-active" className="ml-auto w-1.5 h-1.5 rounded-full bg-accent" />}
  </button>
);

const Card = ({ children, className, title, subtitle }: { children: React.ReactNode, className?: string, title?: string, subtitle?: string }) => (
  <div className={cn("bg-surface border border-line rounded-sm flex flex-col overflow-hidden", className)}>
    {(title || subtitle) && (
      <div className="bg-header px-3 py-2 border-b border-line flex justify-between items-center">
        <h3 className="text-[10px] font-bold text-ink-bright uppercase tracking-widest">{title}</h3>
        {subtitle && <span className="mono-label">{subtitle}</span>}
      </div>
    )}
    <div className="p-3 flex-1 flex flex-col gap-3">
      {children}
    </div>
  </div>
);

const Badge = ({ children, variant = 'default' }: { children: React.ReactNode, variant?: 'default' | 'success' | 'warning' | 'danger' }) => {
  const styles = {
    default: "bg-line text-ink/60 border-line/50",
    success: "bg-success/10 text-success border-success/30",
    warning: "bg-warning/10 text-warning border-warning/30",
    danger: "bg-danger/10 text-danger border-danger/30",
  };
  return (
    <span className={cn("px-1 py-0.5 rounded-xs text-[9px] font-bold border uppercase tracking-tighter", styles[variant])}>
      {children}
    </span>
  );
};

// --- AI Assistant ---
const AIAssistant = () => {
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [messages, setMessages] = useState<AssistantMessage[]>([
    { 
      role: 'assistant', 
      content: `Welcome to Unity NPC Core Assistant. How can I help with your workflow?`
    }
  ]);
  const [suggestions, setSuggestions] = useState<string[]>([]);

  useEffect(() => {
    fetchOptionalJson<string[]>('/api/suggestions').then((data) => {
      if (data) setSuggestions(data);
    });
  }, []);

  const askAI = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim() || loading) return;

    const userMsg = query;
    setQuery('');
    setMessages(prev => [...prev, { role: 'user', content: userMsg }]);
    setLoading(true);

    try {
      const response = await fetch('/api/assistant', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: userMsg,
          history: messages,
        }),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(payload.error || 'Assistant request failed.');
      }

      setMessages(prev => [...prev, { role: 'assistant', content: payload.content || "Error processing request." }]);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Connection failed.';
      setMessages(prev => [...prev, { role: 'assistant', content: `Error: ${message}` }]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <aside className="w-64 border-r border-line bg-surface flex flex-col overflow-hidden">
      <div className="p-3 border-b border-line bg-panel">
        <h2 className="text-[11px] font-bold text-ink-bright uppercase tracking-wider mb-2">Workflow Assistant</h2>
        <div className="p-2 bg-accent/5 border border-accent/20 rounded text-[11px] leading-relaxed italic text-accent animate-in fade-in">
          {messages[messages.length - 1].content}
        </div>
      </div>
      
      <div className="flex-1 overflow-hidden p-3 flex flex-col gap-3">
        {/* Dynamic Context Hint */}
        <div className="flex flex-col gap-1">
          <span className="text-[9px] uppercase font-bold text-accent tracking-widest flex items-center gap-1">
            <Sparkles className="w-2 h-2" />
            Live Suggestions
          </span>
          <div className="p-2 border border-accent/20 rounded bg-accent/5 text-[10px] text-accent/80 italic leading-snug">
            {suggestions.length > 0 ? suggestions[Math.floor(Math.random() * suggestions.length)] : "System suggests checking Rank size for QuestGiver LoRA if loss plateau persists."}
          </div>
        </div>

        <div className="flex flex-col gap-1">
          <span className="text-[9px] uppercase font-bold text-ink/40 tracking-widest">Active Documentation</span>
          <div className="p-2 border border-line rounded bg-bg text-[10px] text-ink/60 cursor-help hover:border-accent/40 transition-colors">
            • dataset_formatting.md<br/>
            • unity_npc_protocol.pdf<br/>
            • dialogue_states_v4.json
          </div>
        </div>

        <div className="mt-auto">
          <form onSubmit={askAI}>
            <textarea 
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); askAI(e); } }}
              className="w-full h-24 bg-bg border border-line rounded p-2 text-[11px] focus:outline-none focus:border-accent transition-colors resize-none mb-1 shadow-inner" 
              placeholder={loading ? "Assistant is thinking..." : "Ask assistant about workflow..."}
            />
            {loading && <div className="text-[9px] text-accent font-bold animate-pulse">PROCESSING_REQUEST...</div>}
          </form>
        </div>
      </div>
    </aside>
  );
};

// --- Main App ---

export default function App() {
  const [activeTab, setActiveTab] = useState<'overview' | 'training' | 'datasets' | 'compare' | 'analytics' | 'commands'>('overview');
  const [jobs, setJobs] = useState<Job[]>([]);
  const [selectedJobIds, setSelectedJobIds] = useState<string[]>([]);
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [logs, setLogs] = useState<string[]>([]);
  const [analyticsData, setAnalyticsData] = useState<Array<{ step: number; loss: number; acc: number; lr: number }>>([]);
  const [availableCommands, setAvailableCommands] = useState<AvailableCommand[]>([]);
  const [subjects, setSubjects] = useState<Subject[]>([]);
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [health, setHealth] = useState<HealthCheck | null>(null);
  const [telemetry, setTelemetry] = useState<Telemetry | null>(null);
  const [runs, setRuns] = useState<RunArtifact[]>([]);
  const [exportArtifacts, setExportArtifacts] = useState<ExportArtifact[]>([]);
  const [activeFilter, setActiveFilter] = useState<'all' | 'running'>('all');
  const [uiError, setUiError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  const [trainingConfig, setTrainingConfig] = useState({
    spec: 'subjects/chemistry_instructor.json',
    preset: 'fast-3b',
    learningRate: '2e-4',
    batchSize: 4,
    epochs: 3,
    rank: 16,
    alpha: 32,
    baseModel: 'mistralai/Mistral-7B-Instruct-v0.2'
  });

  const fetchJson = async <T,>(url: string): Promise<T> => {
    const response = await fetch(url);
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(payload.error || `Request failed: ${url}`);
    }
    return response.json() as Promise<T>;
  };

  const fetchOptionalJson = async <T,>(url: string): Promise<T | null> => {
    try {
      return await fetchJson<T>(url);
    } catch {
      return null;
    }
  };

  const downloadCsv = (rows: string[][], fileName: string) => {
    const csv = rows.map((row) => row.map((cell) => `"${String(cell).replace(/"/g, '""')}"`).join(',')).join('\n');
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');
    const url = URL.createObjectURL(blob);
    link.href = url;
    link.setAttribute('download', fileName);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  const exportJobsCsv = () => {
    const rows = [
      ['id', 'name', 'type', 'status', 'progress', 'loss', 'createdAt', 'startedAt', 'finishedAt'],
      ...jobs.map((job) => [
        job.id,
        job.name,
        job.type,
        job.status,
        job.progress,
        job.loss ?? '',
        job.createdAt,
        job.startedAt ?? '',
        job.finishedAt ?? '',
      ]),
    ];
    downloadCsv(rows, 'ucore_jobs.csv');
  };

  const stopAllJobs = async () => {
    const runningJobs = jobs.filter((job) => job.status === 'running');
    if (runningJobs.length === 0) {
      setUiError('No running jobs to stop.');
      return;
    }
    setIsLoading(true);
    try {
      await Promise.all(runningJobs.map((job) => fetch('/api/commands/stop', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: job.id }),
      })));
      await fetchData();
    } catch (error) {
      setUiError(error instanceof Error ? error.message : 'Failed to stop running jobs');
    } finally {
      setIsLoading(false);
    }
  };

  const toggleExecutionMode = async () => {
    if (!status) return;
    const nextMode = status.executionMode === 'local' ? 'remote' : 'local';
    try {
      const response = await fetch('/api/execution-mode', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode: nextMode }),
      });
      if (!response.ok) {
        const err = await response.json().catch(() => ({}));
        throw new Error(err.error || 'Failed to toggle execution mode');
      }
      const result = await response.json();
      setStatus((prev) => prev ? { ...prev, executionMode: result.mode } : prev);
      setUiError(null);
    } catch (error) {
      setUiError(error instanceof Error ? error.message : 'Failed to toggle execution mode');
    }
  };

  const fetchData = async () => {
    setIsLoading(true);
    try {
      const [jobsData, logsData, datasetsData, commandsData, subjectsData, statusData] = await Promise.all([
        fetchJson<Job[]>('/api/jobs'),
        fetchJson<string[]>('/api/logs'),
        fetchJson<Dataset[]>('/api/datasets'),
        fetchJson<AvailableCommand[]>('/api/available-commands'),
        fetchJson<Subject[]>('/api/subjects'),
        fetchJson<SystemStatus>('/api/system/status'),
      ]);
      const [healthData, runsData, exportsData, telemetryData] = await Promise.all([
        fetchOptionalJson<HealthCheck>('/api/health'),
        fetchOptionalJson<RunArtifact[]>('/api/runs'),
        fetchOptionalJson<ExportArtifact[]>('/api/exports'),
        fetchOptionalJson<Telemetry>('/api/telemetry'),
      ]);
      setJobs(jobsData);
      setLogs(logsData);
      setDatasets(datasetsData);
      setAvailableCommands(commandsData);
      setSubjects(subjectsData);
      setStatus(statusData);
      setHealth(healthData);
      setTelemetry(telemetryData);
      setRuns(runsData ?? []);
      setExportArtifacts(exportsData ?? []);
      setUiError(null);
    } catch (error) {
      setUiError(error instanceof Error ? error.message : 'Failed to fetch data');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 5000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    const targetJobId = selectedJobId || jobs[0]?.id;
    if (!targetJobId) {
      setAnalyticsData([]);
      return;
    }

    fetchJson<Array<{ step: number; loss: number; acc: number; lr: number }>>(`/api/analytics?jobId=${encodeURIComponent(targetJobId)}`)
      .then(setAnalyticsData)
      .catch(() => setAnalyticsData([]));
  }, [selectedJobId, jobs]);

  const filteredJobs = activeFilter === 'running' ? jobs.filter((job) => job.status === 'running') : jobs;

  const toggleJobSelection = (e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    setSelectedJobIds(prev => 
      prev.includes(id) ? prev.filter(i => i !== id) : [...prev, id]
    );
  };

  const triggerCommand = async (payload: Record<string, unknown>) => {
    const response = await fetch('/api/commands/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    if (!response.ok) {
      const err = await response.json().catch(() => ({}));
      throw new Error(err.error || 'Failed to start command');
    }
    await fetchData();
  };

  const getDefaultPayloadForCommand = (commandId: string): Record<string, unknown> => {
    const derivedNpcKey = trainingConfig.spec.replace('subjects/', '').replace('.json', '');
    switch (commandId) {
      case 'dataset-generate':
      case 'train':
      case 'pipeline':
        return { spec: trainingConfig.spec, preset: trainingConfig.preset };
      case 'export':
        return { npcKey: derivedNpcKey, options: { modelId: trainingConfig.baseModel } };
      case 'export-adapter':
        return { npcKey: derivedNpcKey };
      default:
        return { spec: trainingConfig.spec };
    }
  };

  const getNestedValue = (obj: Record<string, unknown>, dotPath: string): unknown => {
    return dotPath.split('.').reduce<unknown>((acc, key) => {
      if (acc && typeof acc === 'object') {
        return (acc as Record<string, unknown>)[key];
      }
      return undefined;
    }, obj);
  };

  const setNestedValue = (obj: Record<string, unknown>, dotPath: string, value: string): Record<string, unknown> => {
    const keys = dotPath.split('.');
    const next = { ...obj };
    let cursor: Record<string, unknown> = next;
    for (let i = 0; i < keys.length - 1; i += 1) {
      const key = keys[i];
      const existing = cursor[key];
      cursor[key] = existing && typeof existing === 'object' ? { ...(existing as Record<string, unknown>) } : {};
      cursor = cursor[key] as Record<string, unknown>;
    }
    cursor[keys[keys.length - 1]] = value;
    return next;
  };

  const triggerCommandFromSystemHub = async (cmd: AvailableCommand) => {
    let payload: Record<string, unknown> = {
      commandId: cmd.id,
      type: cmd.type,
      ...getDefaultPayloadForCommand(cmd.id),
    };

    for (const field of cmd.requiredFields) {
      const existingValue = getNestedValue(payload, field);
      if (typeof existingValue === 'string' && existingValue.trim()) continue;
      const provided = window.prompt(`Provide required field: ${field}`);
      if (!provided || !provided.trim()) {
        throw new Error(`Missing required field: ${field}`);
      }
      payload = setNestedValue(payload, field, provided.trim());
    }

    await triggerCommand(payload);
  };

  const stopJob = async (id: string) => {
    const response = await fetch('/api/commands/stop', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id }),
    });
    if (!response.ok) {
      const err = await response.json().catch(() => ({}));
      setUiError(err.error || 'Failed to stop job');
      return;
    }
    await fetchData();
  };

  return (
    <div className="flex flex-col h-screen overflow-hidden bg-bg text-ink font-sans border border-line selection:bg-accent/30 selection:text-ink-bright">
      {/* Top Global Monitor */}
      <header className="h-12 border-b border-line bg-header flex items-center justify-between px-4 shrink-0 z-50">
        <div className="flex items-center gap-6">
          <div className="flex items-center gap-2 text-accent">
            <div className="w-2 h-2 rounded-full bg-accent glow-blue"></div>
            <span className="font-mono text-xs font-bold tracking-widest uppercase">Unity NPC Core v2.4</span>
          </div>
          <div className="h-4 w-px bg-line"></div>
          <div className="flex gap-4">
            <div className="flex flex-col">
              <span className="text-[9px] uppercase opacity-50 font-bold tracking-tighter">{telemetry?.gpuName ?? 'GPU'}</span>
              <span className={cn("text-xs font-mono font-bold", telemetry && telemetry.gpuLoad > 90 ? "text-danger" : "text-success")}>
                {telemetry ? `${telemetry.gpuLoad}% LOAD` : 'N/A'}
              </span>
            </div>
            <div className="flex flex-col">
              <span className="text-[9px] uppercase opacity-50 font-bold tracking-tighter">CPU LOAD</span>
               <span className={cn("text-xs font-mono text-accent font-bold", telemetry && telemetry.cpuLoad > 75 ? "text-danger" : "text-success")}>{telemetry ? `${telemetry.cpuLoad}%` : 'N/A'}</span>
            </div>
          </div>
        </div>
        <div className="flex items-center gap-4">
          <div className="flex flex-col text-right">
             <span className="text-[9px] uppercase opacity-50 font-bold tracking-tighter">SYSTEM HEALTH</span>
             <span className={cn("text-[10px] font-bold", health?.ok ? "text-success" : "text-warning")}>{health?.ok ? 'HEALTHY' : 'DEGRADED'}</span>
          </div>
          <div className="h-8 w-px bg-line" />
          <button onClick={stopAllJobs} className="px-3 py-1 bg-danger/20 text-danger border border-danger/40 text-[10px] font-bold rounded-sm uppercase tracking-tighter hover:bg-danger/40 transition-colors active:scale-95">
            Emergency Kill
          </button>
        </div>
      </header>

      <div className="flex flex-1 overflow-hidden">
        {/* Left Sidebar: Assistant/Docs */}
        <AIAssistant />

        {/* Main Content: Matrix & Logs */}
        <main className="flex-1 flex flex-col overflow-hidden bg-bg">
          {/* Tab Selection */}
          <div className="flex px-4 border-b border-line bg-surface/50">
            <button 
              onClick={() => setActiveTab('overview')}
              className={cn(
                "px-4 py-2 text-[10px] font-bold uppercase tracking-widest border-b-2 transition-colors",
                activeTab === 'overview' ? "border-accent text-ink-bright" : "border-transparent text-ink/40 hover:text-ink/60"
              )}
            >
              Operations Matrix
            </button>
            <button 
              onClick={() => setActiveTab('datasets')}
              className={cn(
                "px-4 py-2 text-[10px] font-bold uppercase tracking-widest border-b-2 transition-colors",
                activeTab === 'datasets' ? "border-accent text-ink-bright" : "border-transparent text-ink/40 hover:text-ink/60"
              )}
            >
              Dataset Factory
            </button>
            <button 
              onClick={() => setActiveTab('training')}
              className={cn(
                "px-4 py-2 text-[10px] font-bold uppercase tracking-widest border-b-2 transition-colors",
                activeTab === 'training' ? "border-accent text-ink-bright" : "border-transparent text-ink/40 hover:text-ink/60"
              )}
            >
              Training Suite
            </button>
            <button 
              onClick={() => setActiveTab('analytics')}
              className={cn(
                "px-4 py-2 text-[10px] font-bold uppercase tracking-widest border-b-2 transition-colors",
                activeTab === 'analytics' ? "border-accent text-ink-bright" : "border-transparent text-ink/40 hover:text-ink/60"
              )}
            >
              TensorBoard
            </button>
            <button 
              onClick={() => setActiveTab('commands')}
              className={cn(
                "px-4 py-2 text-[10px] font-bold uppercase tracking-widest border-b-2 transition-colors",
                activeTab === 'commands' ? "border-accent text-ink-bright" : "border-transparent text-ink/40 hover:text-ink/60"
              )}
            >
              System Hub
            </button>
            <button 
              onClick={() => setActiveTab('compare')}
              className={cn(
                "px-4 py-2 text-[10px] font-bold uppercase tracking-widest border-b-2 transition-colors relative",
                activeTab === 'compare' ? "border-accent text-ink-bright" : "border-transparent text-ink/40 hover:text-ink/60"
              )}
            >
              Model Comparison
              {selectedJobIds.length > 0 && (
                <span className="ml-2 bg-accent text-bg px-1 rounded-full text-[8px]">
                  {selectedJobIds.length}
                </span>
              )}
            </button>
          </div>

          <AnimatePresence mode="wait">
            {activeTab === 'overview' && (
              <motion.div 
                key="overview"
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: 10 }}
                className="flex-1 flex flex-col overflow-hidden"
              >
                {/* Matrix Section */}
                <section className="flex-1 p-4 flex flex-col overflow-hidden">
                  <div className="flex justify-between items-end mb-3">
                    <div className="flex items-center gap-3">
                      <h3 className="text-xs font-bold text-ink-bright uppercase tracking-widest">LoRA Training Performance Matrix</h3>
                      {selectedJobIds.length >= 1 && (
                        <button 
                          onClick={() => setActiveTab('compare')}
                          className="px-2 py-0.5 bg-accent/20 border border-accent/40 text-accent text-[10px] font-bold rounded-sm animate-in zoom-in"
                        >
                          OPEN COMPARISON ({selectedJobIds.length})
                        </button>
                      )}
                    </div>
                    <div className="flex gap-2">
                      <button
                        onClick={() => setActiveFilter((prev) => (prev === 'all' ? 'running' : 'all'))}
                        className={cn(
                          "px-2 py-1 rounded text-[10px] font-bold transition-all",
                          activeFilter === 'running'
                            ? "bg-accent text-bg border border-accent"
                            : "bg-panel border border-line text-ink/60 hover:bg-white/5"
                        )}
                      >
                        Filter: {activeFilter === 'all' ? 'Active' : 'All'}
                      </button>
                      <button
                        onClick={exportJobsCsv}
                        className="px-2 py-1 bg-panel border border-line text-[10px] text-ink/60 rounded hover:bg-white/5 transition-colors"
                      >
                        Export CSV
                      </button>
                    </div>
                  </div>
                  
                  <div className="flex-1 border border-line rounded-sm overflow-hidden bg-surface">
                    <div className="overflow-auto h-full">
                      <table className="w-full text-left border-collapse table-fixed">
                        <thead className="sticky top-0 z-10">
                          <tr className="bg-header text-[10px] text-ink/50 uppercase">
                            <th className="p-2 border-b border-line font-bold tracking-wider w-8">
                               <div className="w-3 h-3 border border-line rounded-sm" />
                            </th>
                            <th className="p-2 border-b border-line font-bold tracking-wider w-1/3">Model / Version</th>
                            <th className="p-2 border-b border-line font-bold tracking-wider text-right">Loss</th>
                            <th className="p-2 border-b border-line font-bold tracking-wider text-right">Prog</th>
                            <th className="p-2 border-b border-line font-bold tracking-wider">Source</th>
                            <th className="p-2 border-b border-line font-bold tracking-wider">Status</th>
                            <th className="p-2 border-b border-line font-bold tracking-wider text-right">Action</th>
                          </tr>
                        </thead>
                        <tbody className="text-[11px] font-mono divide-y divide-line/30">
                          {filteredJobs.map((job) => (
                            <tr 
                              key={job.id} 
                              onClick={() => setSelectedJobId(job.id)}
                              className={cn(
                                "hover:bg-accent/5 transition-colors cursor-pointer",
                                job.status === 'running' ? "bg-accent/5" : "",
                                selectedJobId === job.id ? "bg-accent/20 border-l-2 border-accent" : "",
                                selectedJobIds.includes(job.id) ? "bg-accent/10" : ""
                              )}
                            >
                              <td className="p-2" onClick={(e) => toggleJobSelection(e, job.id)}>
                                <div className={cn(
                                  "w-3 h-3 border rounded-sm flex items-center justify-center transition-colors",
                                  selectedJobIds.includes(job.id) ? "bg-accent border-accent" : "border-line"
                                )}>
                                  {selectedJobIds.includes(job.id) && <div className="w-1.5 h-1.5 bg-bg rounded-full" />}
                                </div>
                              </td>
                              <td className="p-2 font-bold text-ink-bright truncate">{job.name}</td>
                              <td className={cn(
                                "p-2 text-right font-bold",
                                job.loss !== null && job.loss < 0.1 ? "text-success" : "text-warning"
                              )}>
                                {job.loss?.toFixed(3) || '--'}
                              </td>
                              <td className="p-2 text-right text-ink/70">{job.progress}%</td>
                              <td className="p-2 text-ink/50 truncate uppercase text-[9px]">{job.type}</td>
                              <td className="p-2">
                                <Badge variant={job.status === 'completed' ? 'success' : job.status === 'running' ? 'warning' : job.status === 'failed' ? 'danger' : 'default'}>
                                  {job.status}
                                </Badge>
                              </td>
                              <td className="p-2 text-right">
                                 {job.status === 'running' ? (
                                   <button onClick={(e) => { e.stopPropagation(); stopJob(job.id); }} className="text-danger hover:underline uppercase text-[9px] font-bold">Stop</button>
                                 ) : (
                                   <button
                                     onClick={(e) => { e.stopPropagation(); setSelectedJobId(job.id); setActiveTab('compare'); }}
                                     className="text-accent hover:underline uppercase text-[9px] font-bold"
                                   >
                                     Manage
                                   </button>
                                 )}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                </section>

                {/* Selected Job Stages Section */}
                <AnimatePresence>
                  {selectedJobId && (
                    <motion.section 
                      initial={{ height: 0, opacity: 0 }}
                      animate={{ height: 'auto', opacity: 1 }}
                      exit={{ height: 0, opacity: 0 }}
                      className="mx-4 mb-4"
                    >
                      {(() => {
                        const job = jobs.find(j => j.id === selectedJobId);
                        if (!job) return null;
                        return (
                          <Card title={`Workflow Tracker: ${job.name}`} subtitle="PIPELINE_INSIGHTS">
                            <WorkflowVisualizer stages={job.stages} />
                            <div className="flex gap-4 mt-2">
                              {job.stages.find(s => s.status === 'running' || s.status === 'completed' && s.logs.length > 0) && (
                                <div className="flex-1 p-2 bg-black/20 rounded border border-line/30 text-[10px] mono-label">
                                  <span className="text-accent underline font-bold mb-1 block">Active Stage Logs:</span>
                                  {job.stages.find(s => s.status === 'running')?.logs.map((l, i) => <div key={i} className="text-ink/60">• {l}</div>) || 
                                   job.stages.find(s => s.status === 'completed')?.logs.map((l, i) => <div key={i} className="text-success/60">• {l}</div>)}
                                </div>
                              )}
                            </div>
                          </Card>
                        );
                      })()}
                    </motion.section>
                  )}
                </AnimatePresence>
              </motion.div>
            )}

            {activeTab === 'training' && (
              <motion.div 
                key="training"
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -10 }}
                className="flex-1 overflow-hidden p-4 flex flex-col gap-6"
              >
                <div className="flex justify-between items-end">
                   <h3 className="text-xs font-bold text-ink-bright uppercase tracking-widest">LoRA Hyperparameter Suite</h3>
                   <div className="flex gap-2 text-[10px] font-mono text-ink/40">
                      <span>LOADER: NF4_QUANT</span>
                      <span className="text-success underline">READY_FOR_INIT</span>
                   </div>
                </div>

                <div className="grid grid-cols-2 gap-4">
                   <Card title="Structural Parameters" subtitle="RANK_AND_DIM">
                      <div className="space-y-4">
                        <div>
                          <label className="text-[9px] uppercase font-bold text-ink/30 mb-1.5 block">Subject Spec</label>
                          <select
                            value={trainingConfig.spec}
                            onChange={(e) => setTrainingConfig({ ...trainingConfig, spec: e.target.value })}
                            className="w-full bg-bg border border-line rounded px-3 py-2 text-xs font-mono focus:border-accent outline-none mb-2"
                          >
                            {subjects.map((subject) => (
                              <option key={subject.id} value={subject.path}>{subject.path}</option>
                            ))}
                          </select>
                          <label className="text-[9px] uppercase font-bold text-ink/30 mb-1.5 block">Preset</label>
                          <input
                            value={trainingConfig.preset}
                            onChange={(e) => setTrainingConfig({ ...trainingConfig, preset: e.target.value })}
                            className="w-full bg-bg border border-line rounded px-3 py-2 text-xs font-mono focus:border-accent outline-none"
                          />
                        </div>
                        <div>
                          <label className="text-[9px] uppercase font-bold text-ink/30 mb-1.5 block">Base Model Path</label>
                          <input 
                            value={trainingConfig.baseModel}
                            onChange={(e) => setTrainingConfig({...trainingConfig, baseModel: e.target.value})}
                            className="w-full bg-bg border border-line rounded px-3 py-2 text-xs font-mono focus:border-accent outline-none"
                          />
                        </div>
                        <div className="grid grid-cols-2 gap-4">
                          <div>
                            <label className="text-[9px] uppercase font-bold text-ink/30 mb-1.5 block">LoRA Rank (R)</label>
                            <input 
                              type="number"
                              value={trainingConfig.rank}
                              onChange={(e) => setTrainingConfig({...trainingConfig, rank: parseInt(e.target.value)})}
                              className="w-full bg-bg border border-line rounded px-3 py-2 text-xs font-mono focus:border-accent outline-none"
                            />
                            <p className="text-[8px] mt-1 text-ink/30">Higher = more capacity but larger file size.</p>
                          </div>
                          <div>
                            <label className="text-[9px] uppercase font-bold text-ink/30 mb-1.5 block">LoRA Alpha</label>
                            <input 
                              type="number"
                              value={trainingConfig.alpha}
                              onChange={(e) => setTrainingConfig({...trainingConfig, alpha: parseInt(e.target.value)})}
                              className="w-full bg-bg border border-line rounded px-3 py-2 text-xs font-mono focus:border-accent outline-none"
                            />
                          </div>
                        </div>
                      </div>
                   </Card>

                   <Card title="Optimization Logic" subtitle="SCHEDULER_V1">
                      <div className="space-y-4">
                        <div>
                          <label className="text-[9px] uppercase font-bold text-ink/30 mb-1.5 block">Learning Rate</label>
                          <div className="flex gap-2">
                             <input 
                                value={trainingConfig.learningRate}
                                onChange={(e) => setTrainingConfig({...trainingConfig, learningRate: e.target.value})}
                                className="flex-1 bg-bg border border-line rounded px-3 py-2 text-xs font-mono focus:border-accent outline-none"
                             />
                             <select className="bg-bg border border-line rounded px-2 text-[10px] text-ink/60 outline-none">
                                <option>Cosine</option>
                                <option>Linear</option>
                                <option>Constant</option>
                             </select>
                          </div>
                        </div>
                        <div className="grid grid-cols-2 gap-4">
                          <div>
                            <label className="text-[9px] uppercase font-bold text-ink/30 mb-1.5 block">Batch Size</label>
                            <select 
                              value={trainingConfig.batchSize}
                              onChange={(e) => setTrainingConfig({...trainingConfig, batchSize: parseInt(e.target.value)})}
                              className="w-full bg-bg border border-line rounded px-3 py-2 text-xs font-mono focus:border-accent outline-none"
                            >
                               <option value={1}>1</option>
                               <option value={2}>2</option>
                               <option value={4}>4</option>
                               <option value={8}>8</option>
                               <option value={16}>16</option>
                            </select>
                          </div>
                          <div>
                            <label className="text-[9px] uppercase font-bold text-ink/30 mb-1.5 block">Epochs</label>
                            <input 
                              type="number"
                              value={trainingConfig.epochs}
                              onChange={(e) => setTrainingConfig({...trainingConfig, epochs: parseInt(e.target.value)})}
                              className="w-full bg-bg border border-line rounded px-3 py-2 text-xs font-mono focus:border-accent outline-none"
                            />
                          </div>
                        </div>
                      </div>
                   </Card>
                </div>

                <div className="mt-auto p-4 bg-accent/5 border border-accent/10 rounded-sm flex justify-between items-center">
                   <div className="space-y-1">
                      <div className="flex items-center gap-2">
                         <Shield className="w-3 h-3 text-success" />
                         <span className="text-[10px] font-bold text-success uppercase tracking-tighter">Config Validation Passed</span>
                      </div>
                      <p className="text-[10px] text-ink/40">Estimated VRAM requirement: 14.8GB (Optimized for 24GB+ cards)</p>
                   </div>
                    <button 
                      onClick={async () => {
                        try {
                          await triggerCommand({
                            commandId: 'train',
                            type: 'Training',
                            spec: trainingConfig.spec,
                            preset: trainingConfig.preset,
                            options: {
                              learningRate: trainingConfig.learningRate,
                              batchSize: trainingConfig.batchSize,
                              epochs: trainingConfig.epochs,
                              rank: trainingConfig.rank,
                              alpha: trainingConfig.alpha,
                              baseModel: trainingConfig.baseModel,
                            },
                          });
                          setActiveTab('overview');
                        } catch (error) {
                          setUiError(error instanceof Error ? error.message : 'Training launch failed');
                        }
                      }}
                      className="px-6 py-2 bg-accent text-bg text-[11px] font-bold rounded-sm uppercase tracking-widest hover:brightness-110 active:scale-95 transition-all shadow-xl shadow-accent/20"
                    >
                      Launch Training Cluster
                   </button>
                </div>
              </motion.div>
            )}

            {activeTab === 'analytics' && (
              <motion.div 
                key="analytics"
                initial={{ opacity: 0, scale: 0.98 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.98 }}
                className="flex-1 overflow-hidden p-4 flex flex-col gap-4"
              >
                <div className="flex justify-between items-end">
                   <h3 className="text-xs font-bold text-ink-bright uppercase tracking-widest">LoRA SCALARS: TRAINING_ACCURACY & LOSS</h3>
                   <div className="flex gap-4 text-[10px] items-center">
                      <div className="flex items-center gap-1.5"><div className="w-2 h-2 bg-accent rounded-sm" /> <span>Current Run</span></div>
                      <div className="flex items-center gap-1.5"><div className="w-2 h-2 bg-line rounded-sm" /> <span>Baseline</span></div>
                      <button onClick={fetchData} className="text-accent underline font-mono">Refresh API</button>
                   </div>
                </div>

                <div className="grid grid-cols-2 gap-4 flex-1 overflow-auto custom-scrollbar">
                   <Card title="Model Loss (Smooth: 0.6)" subtitle="TAG: TRAIN/LOSS">
                      <div className="h-64 mt-4">
                        <ResponsiveContainer width="100%" height="100%">
                          <LineChart data={analyticsData}>
                            <CartesianGrid strokeDasharray="3 3" stroke="var(--line)" opacity={0.3} />
                            <XAxis dataKey="step" stroke="var(--ink)" fontSize={9} opacity={0.5} />
                            <YAxis stroke="var(--ink)" fontSize={9} opacity={0.5} />
                            <Tooltip 
                              contentStyle={{ background: 'var(--header)', border: '1px solid var(--line)', borderRadius: '4px', fontSize: '10px' }}
                            />
                            <Line type="monotone" dataKey="loss" stroke="var(--accent)" strokeWidth={2} dot={{ r: 2 }} />
                          </LineChart>
                        </ResponsiveContainer>
                      </div>
                   </Card>

                   <Card title="Validation Accuracy" subtitle="TAG: EVAL/ACC">
                      <div className="h-64 mt-4">
                        <ResponsiveContainer width="100%" height="100%">
                          <AreaChart data={analyticsData}>
                            <defs>
                              <linearGradient id="colorAcc" x1="0" y1="0" x2="0" y2="1">
                                <stop offset="5%" stopColor="var(--success)" stopOpacity={0.2}/>
                                <stop offset="95%" stopColor="var(--success)" stopOpacity={0}/>
                              </linearGradient>
                            </defs>
                            <CartesianGrid strokeDasharray="3 3" stroke="var(--line)" opacity={0.3} />
                            <XAxis dataKey="step" stroke="var(--ink)" fontSize={9} opacity={0.5} />
                            <YAxis stroke="var(--ink)" fontSize={9} opacity={0.5} />
                            <Tooltip 
                              contentStyle={{ background: 'var(--header)', border: '1px solid var(--line)', borderRadius: '4px', fontSize: '10px' }}
                            />
                            <Area type="monotone" dataKey="acc" stroke="var(--success)" fillOpacity={1} fill="url(#colorAcc)" />
                          </AreaChart>
                        </ResponsiveContainer>
                      </div>
                   </Card>

                   <Card title="Learning Rate Scheduler" subtitle="TAG: OPTIM/LR" className="col-span-2">
                      <div className="h-48 mt-4">
                        <ResponsiveContainer width="100%" height="100%">
                          <LineChart data={analyticsData}>
                            <CartesianGrid strokeDasharray="3 3" stroke="var(--line)" opacity={0.3} />
                            <XAxis dataKey="step" stroke="var(--ink)" fontSize={9} opacity={0.5} />
                            <YAxis stroke="var(--ink)" fontSize={9} opacity={0.5} />
                            <Line type="stepAfter" dataKey="lr" stroke="var(--warning)" strokeWidth={2} dot={false} />
                          </LineChart>
                        </ResponsiveContainer>
                      </div>
                   </Card>
                </div>
              </motion.div>
            )}

            {activeTab === 'commands' && (
              <motion.div 
                key="commands"
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -10 }}
                className="flex-1 overflow-hidden p-4 flex flex-col gap-6"
              >
                <div className="flex justify-between items-end">
                   <h3 className="text-xs font-bold text-ink-bright uppercase tracking-widest">Global System Command Hub</h3>
                   <p className="text-[10px] text-ink/40 font-mono italic">Direct Access to Core PIDs and Asset Handlers</p>
                </div>

                <div className="grid grid-cols-3 gap-4">
                   {availableCommands.map((cmd) => (
                       <button 
                        key={cmd.id}
                          onClick={async () => {
                            try {
                              await triggerCommandFromSystemHub(cmd);
                            } catch (error) {
                              setUiError(error instanceof Error ? error.message : 'Command failed');
                            }
                          }}
                        className={cn(
                          "p-4 border border-line rounded flex flex-col items-center gap-3 transition-all hover:scale-[1.02] active:scale-95 group",
                          cmd.color === 'accent' ? "hover:border-accent bg-accent/5" :
                          cmd.color === 'success' ? "hover:border-success bg-success/5" :
                          cmd.color === 'warning' ? "hover:border-warning bg-warning/5" :
                          cmd.color === 'danger' ? "hover:border-danger bg-danger/5" : "hover:border-ink bg-panel"
                        )}
                      >
                         <div className={cn(
                           "p-2 rounded-sm border border-line transition-colors",
                           cmd.color === 'accent' ? "text-accent border-accent/20" :
                           cmd.color === 'success' ? "text-success border-success/20" :
                           cmd.color === 'warning' ? "text-warning border-warning/20" :
                           cmd.color === 'danger' ? "text-danger border-danger/20" : "text-ink/40"
                         )}>
                            {cmd.icon === 'zap' && <Zap className="w-5 h-5" />}
                            {cmd.icon === 'external-link' && <ExternalLink className="w-5 h-5" />}
                            {cmd.icon === 'layers' && <Layers className="w-5 h-5" />}
                            {cmd.icon === 'x-circle' && <XCircle className="w-5 h-5" />}
                            {cmd.icon === 'database' && <Database className="w-5 h-5" />}
                         </div>
                         <span className="text-[11px] font-bold uppercase tracking-tighter text-ink-bright text-center">{cmd.label}</span>
                         <span className="text-[8px] opacity-30 font-mono">READY_EXEC</span>
                      </button>
                   ))}
                </div>

                <Card title="Quick Terminal Access" subtitle="SH_ROOT@NPC_CORE">
                   <div className="bg-black/60 rounded p-4 font-mono text-[11px] text-accent/80 space-y-2 h-48 overflow-y-auto custom-scrollbar">
                      <div className="flex gap-2">
                         <span className="text-success">$</span>
                         <span>ssh-agent auth --key=/mnt/vram/core_v4</span>
                      </div>
                      <div className="text-ink/40">[AUTH] RSA_TOKEN_VALIDATED (A100_NODE_X2)</div>
                      <div className="flex gap-2">
                         <span className="text-success">$</span>
                         <span className="animate-pulse">_</span>
                      </div>
                   </div>
                </Card>
              </motion.div>
            )}

            {activeTab === 'compare' && (
              <motion.div 
                key="compare"
                initial={{ opacity: 0, scale: 0.98 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.98 }}
                className="flex-1 overflow-hidden p-4 flex flex-col gap-6"
              >
                <div className="flex justify-between items-end">
                   <h3 className="text-xs font-bold text-ink-bright uppercase tracking-widest">Selected Model Comparison</h3>
                   <div className="flex gap-2">
                      <button 
                        onClick={() => setSelectedJobIds([])}
                        className="px-3 py-1 bg-panel border border-line text-[10px] text-ink/60 rounded uppercase"
                      >
                        Clear Selection
                      </button>
                      <button className="px-3 py-1 bg-accent text-bg text-[10px] font-bold rounded uppercase">Generate Report</button>
                   </div>
                </div>

                {selectedJobIds.length === 0 ? (
                  <div className="flex-1 flex flex-col items-center justify-center border-2 border-dashed border-line rounded-lg text-ink/30 italic">
                    <Layers className="w-12 h-12 mb-4 opacity-20" />
                    <p className="text-sm">No models selected for comparison.</p>
                    <button onClick={() => setActiveTab('overview')} className="mt-4 text-accent text-xs font-bold underline">Go back to Matrix</button>
                  </div>
                ) : (
                  <div className="flex-1 overflow-x-auto overflow-y-hidden custom-scrollbar pb-4">
                    <div className="flex gap-4 h-full min-w-max">
                      {selectedJobIds.map(id => {
                        const job = jobs.find(j => j.id === id);
                        if (!job) return null;
                        return (
                          <div key={job.id} className="w-[320px] bg-surface border border-line rounded-sm flex flex-col overflow-hidden animate-in fade-in slide-in-from-right-4">
                            <div className="p-4 bg-header border-b border-line flex justify-between items-center">
                               <div className="truncate">
                                  <h4 className="text-sm font-bold text-ink-bright truncate">{job.name}</h4>
                                  <p className="text-[10px] opacity-40 font-mono italic">#{job.id}</p>
                               </div>
                               <button onClick={(e) => toggleJobSelection(e, job.id)} className="text-ink/20 hover:text-danger p-1">
                                  <XCircle className="w-4 h-4" />
                               </button>
                            </div>
                            
                            <div className="flex-1 p-4 space-y-6 overflow-y-auto">
                               <div>
                                  <span className="text-[9px] uppercase font-bold text-ink/30 tracking-widest block mb-2">Performance Metrics</span>
                                  <div className="grid grid-cols-2 gap-2">
                                     <div className="p-2 border border-line/50 rounded-sm bg-bg/30">
                                        <p className="text-[9px] opacity-40 uppercase">Loss</p>
                                        <p className="text-lg font-bold text-accent">{job.loss?.toFixed(4) || '--'}</p>
                                     </div>
                                     <div className="p-2 border border-line/50 rounded-sm bg-bg/30">
                                        <p className="text-[9px] opacity-40 uppercase">Progress</p>
                                        <p className="text-lg font-bold text-ink-bright">{job.progress}%</p>
                                     </div>
                                  </div>
                               </div>

                               <div>
                                  <span className="text-[9px] uppercase font-bold text-ink/30 tracking-widest block mb-2">Technical Config</span>
                                  <div className="space-y-2 text-[10px]">
                                     <div className="flex justify-between py-1 border-b border-line/10">
                                        <span className="text-ink/40">Model Engine</span>
                                        <span className="text-ink-bright font-mono">{job.type}</span>
                                     </div>
                                     <div className="flex justify-between py-1 border-b border-line/10">
                                        <span className="text-ink/40">Compute Node</span>
                                        <span className="text-ink-bright font-mono">A100_NODE_X2</span>
                                     </div>
                                     <div className="flex justify-between py-1 border-b border-line/10">
                                        <span className="text-ink/40">Created At</span>
                                        <span className="text-ink-bright font-mono italic">{new Date(job.createdAt).toLocaleDateString()}</span>
                                     </div>
                                  </div>
                               </div>

                               <div className="flex-1">
                                  <span className="text-[9px] uppercase font-bold text-ink/30 tracking-widest block mb-2">Workflow Stages</span>
                                  <div className="space-y-2">
                                     {job.stages.map((s, i) => (
                                        <div key={i} className="flex items-center gap-2 text-[10px]">
                                           <div className={cn(
                                              "w-1.5 h-1.5 rounded-full",
                                              s.status === 'completed' ? "bg-success" :
                                              s.status === 'running' ? "bg-warning" :
                                              s.status === 'failed' ? "bg-danger" : "bg-line"
                                            )} />
                                            <span className={cn(
                                              s.status === 'failed' ? "text-danger" :
                                              s.status === 'pending' ? "text-ink/20" : "text-ink/70"
                                            )}>{s.name}</span>
                                         </div>
                                      ))}
                                  </div>
                                </div>

                                <div className="pt-4 border-t border-line/20">
                                   <button className="w-full py-2 bg-accent/10 border border-accent/20 text-accent text-[10px] font-bold rounded uppercase hover:bg-accent/20 transition-colors">
                                      View Artifacts
                                   </button>
                                </div>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}
              </motion.div>
            )}

            {activeTab === 'datasets' && (
              <motion.div 
                key="datasets"
                initial={{ opacity: 0, x: 10 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -10 }}
                className="flex-1 overflow-hidden p-4 flex flex-col gap-4"
              >
                <div className="flex justify-between items-end">
                  <h3 className="text-xs font-bold text-ink-bright uppercase tracking-widest">Dataset Versioning & Control</h3>
                  <button onClick={async () => {
                    try {
                      await triggerCommand({ commandId: 'dataset-generate', type: 'Dataset', spec: trainingConfig.spec });
                    } catch (error) {
                      setUiError(error instanceof Error ? error.message : 'Dataset generation failed');
                    }
                  }} className="px-3 py-1 bg-accent text-bg text-[10px] font-bold rounded-sm uppercase tracking-tighter hover:brightness-110 active:scale-95 transition-all">
                    Generate from Spec
                  </button>
                </div>

                <div className="grid grid-cols-2 gap-4 flex-1 overflow-hidden">
                  <Card title="Available Datasets" subtitle="LOCAL_FLAT_DB" className="flex-1">
                    <div className="space-y-4">
                      {datasets.map(ds => (
                        <div key={ds.id} className="p-3 bg-panel border border-line rounded flex flex-col gap-3 group hover:border-accent transition-colors">
                          <div className="flex justify-between items-start">
                            <div>
                              <h4 className="text-sm font-bold text-ink-bright">{ds.name}</h4>
                              <p className="text-[10px] text-ink/40 font-mono">ID: {ds.id}</p>
                            </div>
                            <Badge variant="success">SYNCED</Badge>
                          </div>
                          
                          <div className="space-y-1">
                            <span className="text-[9px] uppercase font-bold text-ink/30 tracking-widest">Version History</span>
                            <div className="space-y-1 max-h-32 overflow-y-auto custom-scrollbar pr-1">
                              {ds.versions.map((v, i) => (
                                <div key={i} className="flex justify-between items-center p-1.5 bg-bg/50 border border-line/20 rounded-sm text-[10px]">
                                  <div className="flex gap-2 items-center">
                                    <span className="font-bold text-accent">{v.tag}</span>
                                    <span className="text-ink/40">• {v.entries} pairs</span>
                                  </div>
                                  <div className="flex gap-2">
                                    <button className="text-accent hover:underline uppercase text-[8px] font-bold">Select</button>
                                    <button className="text-ink/20 hover:text-ink/60 uppercase text-[8px] font-bold">Details</button>
                                  </div>
                                </div>
                              ))}
                            </div>
                          </div>

                          <div className="flex gap-2 mt-auto pt-2 border-t border-line/20">
                            <button className="flex-1 py-1.5 bg-accent/5 border border-accent/20 text-accent text-[10px] font-bold rounded uppercase hover:bg-accent/10 transition-colors">Compare v1 vs v2</button>
                            <button className="p-1.5 bg-line/20 border border-line/30 rounded hover:bg-line/40 transition-colors">
                              <ExternalLink className="w-3 h-3 text-ink/40" />
                            </button>
                          </div>
                        </div>
                      ))}
                      {datasets.length === 0 && <div className="text-[10px] text-ink/40">No datasets found in datasets/*</div>}
                    </div>
                  </Card>

                  <Card title="Dataset Analytics" subtitle="QUALITY_SCORE">
                    <div className="space-y-6">
                      <div className="p-4 bg-accent/5 border border-accent/10 rounded-sm text-center">
                         <span className="text-[10px] uppercase font-bold text-accent tracking-widest block mb-2">Global Semantic Coverage</span>
                         <div className="text-3xl font-bold text-ink-bright">94.2<span className="text-accent">%</span></div>
                         <p className="text-[10px] text-ink/40 mt-1">Calculated across 4.5k entries</p>
                      </div>

                      <div className="space-y-3">
                         <h5 className="text-[10px] font-bold text-ink/40 uppercase tracking-widest">Intent Distribution</h5>
                         {[
                           { label: 'Informational', val: 65 },
                           { label: 'Transactional', val: 20 },
                           { label: 'Hostile', val: 10 },
                           { label: 'Fearful', val: 5 },
                         ].map((item, i) => (
                           <div key={i} className="space-y-1">
                             <div className="flex justify-between text-[10px]">
                               <span>{item.label}</span>
                               <span className="font-bold">{item.val}%</span>
                             </div>
                             <div className="h-1 w-full bg-line rounded-full overflow-hidden">
                               <div className="h-full bg-accent" style={{ width: `${item.val}%` }} />
                             </div>
                           </div>
                         ))}
                      </div>
                    </div>
                  </Card>

                  <Card title="Recent Runs & Exports" subtitle="ARTIFACTS">
                    <div className="space-y-4">
                      <div>
                        <div className="flex justify-between items-center mb-2">
                          <span className="text-[10px] uppercase font-bold text-ink/40 tracking-widest">Runs</span>
                          <span className="text-[10px] font-mono text-ink/50">{runs.length}</span>
                        </div>
                        <div className="space-y-2 max-h-40 overflow-y-auto custom-scrollbar pr-1">
                          {runs.length > 0 ? runs.map((run) => (
                            <div key={run.id} className="p-2 bg-bg/70 border border-line/20 rounded-sm text-[10px]">
                              <div className="flex justify-between gap-2">
                                <span className="font-bold truncate">{run.npcKey}</span>
                                <span className="text-ink/40">{new Date(run.updatedAt).toLocaleDateString()}</span>
                              </div>
                              <div className="text-ink/60 text-[9px]">{run.id}</div>
                            </div>
                          )) : <div className="text-[10px] text-ink/40">No active runs found.</div>}
                        </div>
                      </div>

                      <div>
                        <div className="flex justify-between items-center mb-2">
                          <span className="text-[10px] uppercase font-bold text-ink/40 tracking-widest">Exports</span>
                          <span className="text-[10px] font-mono text-ink/50">{exportArtifacts.length}</span>
                        </div>
                        <div className="space-y-2 max-h-40 overflow-y-auto custom-scrollbar pr-1">
                          {exportArtifacts.length > 0 ? exportArtifacts.map((artifact) => (
                            <div key={`${artifact.npcKey}-${artifact.file}`} className="p-2 bg-bg/70 border border-line/20 rounded-sm text-[10px]">
                              <div className="flex justify-between gap-2">
                                <span className="font-bold truncate">{artifact.npcKey}</span>
                                <span className="text-ink/40">{new Date(artifact.updatedAt).toLocaleDateString()}</span>
                              </div>
                              <div className="text-ink/60 text-[9px] truncate">{artifact.file}</div>
                            </div>
                          )) : <div className="text-[10px] text-ink/40">No export artifacts found.</div>}
                        </div>
                      </div>
                    </div>
                  </Card>
                </div>
              </motion.div>
            )}
          </AnimatePresence>

          {/* Logs Section */}
          <section className="h-52 border-t border-line bg-bg p-3 overflow-hidden flex flex-col group">
            <div className="flex justify-between items-center mb-2">
              <span className="text-[10px] font-bold text-ink/40 uppercase tracking-widest">Real-time Log Streams</span>
              <div className="flex gap-2 text-[9px] font-mono text-ink/30">
                <span>PID: 8842</span>
                <span className="text-accent underline">DEBUG_ACTIVE</span>
              </div>
            </div>
            <div className="flex-1 bg-black/40 border border-line rounded p-2 overflow-y-auto font-mono text-[10px] leading-tight space-y-0.5 custom-scrollbar">
              {uiError && <div className="text-danger">[ERROR] {uiError}</div>}
              {isLoading && <div className="text-warning">[INFO] Refreshing dashboard state...</div>}
              {logs.map((log, i) => (
                <div key={i} className="flex gap-2 hover:bg-white/5 px-1 rounded transition-colors">
                  <span className="text-accent opacity-60">[{new Date().toLocaleTimeString([], { hour12: false })}]</span>
                  <span className={cn(
                    log.includes('[ERROR]') ? "text-danger" : 
                    log.includes('[SYSTEM]') ? "text-success" : 
                    log.includes('[DEBUG]') ? "text-warning" : "text-ink/60"
                  )}>
                    {log}
                  </span>
                </div>
              ))}
              <div className="inline-block w-1.5 h-3 bg-accent animate-pulse align-middle ml-1" />
            </div>
          </section>
        </main>

        {/* Right Sidebar: Command Center */}
        <aside className="w-64 border-l border-line bg-surface flex flex-col shrink-0">
          <div className="p-4 flex flex-col gap-6">
            <div>
              <h4 className="text-[10px] font-bold text-ink/40 uppercase tracking-widest mb-3">Workflow Controls</h4>
              <div className="grid grid-cols-1 gap-2">
                <button 
                  onClick={async () => {
                    try {
                      await triggerCommand({ commandId: 'dataset-generate', type: 'Dataset', spec: trainingConfig.spec });
                    } catch (error) {
                      setUiError(error instanceof Error ? error.message : 'Dataset generation failed');
                    }
                  }}
                  className="w-full py-2 bg-accent hover:bg-accent/80 text-bg rounded-sm text-[11px] font-bold uppercase transition-all active:scale-95 shadow-lg shadow-accent/20"
                >
                   Run Dataset Generator
                </button>
                <button 
                  onClick={async () => {
                    try {
                      await triggerCommand({
                        commandId: 'train',
                        type: 'Training',
                        spec: trainingConfig.spec,
                        preset: trainingConfig.preset,
                        options: {
                          model: trainingConfig.baseModel,
                          learningRate: trainingConfig.learningRate,
                          batchSize: trainingConfig.batchSize,
                          epochs: trainingConfig.epochs,
                          rank: trainingConfig.rank,
                          alpha: trainingConfig.alpha,
                        },
                      });
                    } catch (error) {
                      setUiError(error instanceof Error ? error.message : 'Training start failed');
                    }
                  }}
                  className="w-full py-2 bg-panel border border-line hover:border-accent text-ink rounded-sm text-[11px] font-bold uppercase transition-colors"
                >
                  Initialize LoRA Train
                </button>
                <button onClick={async () => {
                  try {
                    await triggerCommand({
                      commandId: 'export',
                      type: 'Export',
                      npcKey: trainingConfig.spec.replace('subjects/', '').replace('.json', ''),
                      options: { modelId: trainingConfig.baseModel },
                    });
                  } catch (error) {
                    setUiError(error instanceof Error ? error.message : 'Export failed');
                  }
                }} className="w-full py-2 bg-panel border border-line hover:border-accent text-ink rounded-sm text-[11px] font-bold uppercase transition-colors">
                  Export for Unity
                </button>
              </div>
            </div>

  {/* Workflow Controls */}
            <div>
              <h4 className="text-[10px] font-bold text-ink/40 uppercase tracking-widest mb-3">Dataset Versions</h4>
              <div className="space-y-2">
                {datasets.map(ds => (
                  <div key={ds.id} className="p-2 bg-panel border border-line rounded flex flex-col gap-1">
                    <div className="flex justify-between items-center">
                      <span className="text-[10px] font-bold text-ink-bright truncate">{ds.name}</span>
                      <Shield className="w-3 h-3 text-success" />
                    </div>
                    <select className="bg-bg text-[10px] border border-line/30 rounded p-1 outline-none text-ink/60">
                      {ds.versions.map(v => (
                        <option key={v.tag}>{v.tag} ({v.entries} entries)</option>
                      ))}
                    </select>
                  </div>
                ))}
                {datasets.length === 0 && <div className="text-[10px] text-ink/40">No datasets detected.</div>}
              </div>
            </div>

            <div>
              <h4 className="text-[10px] font-bold text-ink/40 uppercase tracking-widest mb-3">Subjects</h4>
              <select value={trainingConfig.spec} onChange={(e) => setTrainingConfig({ ...trainingConfig, spec: e.target.value })} className="w-full bg-bg text-[10px] border border-line/30 rounded p-1.5 outline-none text-ink/60">
                {subjects.map((subject) => (
                  <option key={subject.id} value={subject.path}>{subject.path}</option>
                ))}
              </select>
            </div>

            <div className="h-px bg-line"></div>

            <div>
              <h4 className="text-[10px] font-bold text-ink/40 uppercase tracking-widest mb-3">Project Status</h4>
              <Card className="bg-bg/50 border-line/40">
                <div className="space-y-4">
                  <div>
                    <div className="flex justify-between items-center text-[10px] mb-1.5">
                      <span className="mono-label">Active Nodes</span>
                      <span className="font-bold">{status ? `${status.runningJobs} / ${status.totalJobs}` : '--'}</span>
                    </div>
                    <div className="h-1 w-full bg-line rounded-full overflow-hidden">
                       <div className="h-full bg-accent" style={{ width: status && status.totalJobs ? `${Math.round((status.runningJobs / status.totalJobs) * 100)}%` : '0%' }} />
                    </div>
                  </div>
                  <div className="flex justify-between items-center gap-2">
                    <div>
                      <div className="text-[10px] uppercase opacity-70">Execution Mode</div>
                      <div className="text-[11px] font-bold">{status?.executionMode?.toUpperCase() || 'LOCAL'}</div>
                    </div>
                    <button
                      onClick={toggleExecutionMode}
                      className="px-2 py-1 bg-panel border border-line text-[10px] rounded-sm hover:border-accent transition-colors"
                    >
                      Switch to {status?.executionMode === 'local' ? 'Remote' : 'Local'}
                    </button>
                  </div>
                  <div>
                    <div className="flex justify-between items-center text-[10px] mb-1.5">
                      <span className="mono-label">Health</span>
                      <span className={cn(
                        "font-bold",
                        health?.ok ? 'text-success' : 'text-danger'
                      )}>
                        {health ? (health.ok ? 'OK' : 'DEGRADED') : 'UNKNOWN'}
                      </span>
                    </div>
                    <div className="space-y-2 text-[10px] text-ink/50">
                      {health ? Object.entries(health.checks).map(([key, value]) => (
                        <div key={key} className="flex justify-between">
                          <span>{key}</span>
                          <span className={value ? 'text-success' : 'text-danger'}>{value ? 'PASS' : 'FAIL'}</span>
                        </div>
                      )) : <div>Health status unavailable.</div>}
                    </div>
                  </div>
                </div>
              </Card>
            </div>

            <div className="mt-4">
              <div className="bg-accent/10 border border-accent/20 p-3 rounded-sm">
                <div className="text-[10px] text-accent font-bold mb-1 flex items-center gap-1">
                  <Zap className="w-3 h-3 fill-current" />
                  LLM TIP
                </div>
                <p className="text-[10px] leading-normal text-ink/80 italic">
                  Adjust temperature to 0.4 for the Bard dataset to prevent repetitive greeting patterns found in v03.
                </p>
              </div>
            </div>
          </div>
        </aside>
      </div>

      {/* Footer Status Bar */}
      <footer className="h-6 bg-header border-t border-line px-4 flex items-center justify-between text-[9px] font-mono text-ink/40">
        <div className="flex gap-4">
          <span>VRAM: {telemetry ? `${telemetry.gpuMemoryUsedGB}GB / ${telemetry.gpuMemoryTotalGB}GB (${telemetry.gpuName})` : 'N/A'}</span>
          <span>NETWORK: {telemetry ? `${telemetry.networkRxMBps.toFixed(1)} / ${telemetry.networkTxMBps.toFixed(1)} MB/s` : 'N/A'}</span>
          <span className="text-success">NODE_UUID: {telemetry?.nodeId ?? 'N/A'}</span>
        </div>
        <div className="flex gap-4 uppercase">
          <div className="flex items-center gap-1.5">
            <div className="w-1.5 h-1.5 rounded-full bg-success" />
            <span className="text-success font-bold">System Healthy</span>
          </div>
          <span>Session: {status?.executionMode?.toUpperCase() || 'LOCAL'}</span>
          <span className="text-ink/20">©2026 NPC_GEN_CORE</span>
        </div>
      </footer>
    </div>
  );
}
