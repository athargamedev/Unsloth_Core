import { useState, useEffect, useRef } from 'react';
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
import { fetchJson } from './api';
import type { AvailableCommand, Job, TrainingConfig, TensorBoardData, HealthCheck } from './api';
import { useJobs } from './hooks/useJobs';
import { useSystemStatus } from './hooks/useSystemStatus';
import { useTelemetry } from './hooks/useTelemetry';
import { useDatasets } from './hooks/useDatasets';
import { useWebSocket } from './hooks/useWebSocket';
import { AIAssistant } from './components/AIAssistant';
import { OperationsMatrix } from './components/OperationsMatrix';
import { DatasetFactory } from './components/DatasetFactory';
import { TrainingSuite } from './components/TrainingSuite';
import { TensorBoardPanel } from './components/TensorBoardPanel';
import { SystemHub } from './components/SystemHub';
import { ModelComparison } from './components/ModelComparison';
import { NpcOverview } from './components/NpcOverview';
import { Card } from './components/Card';
import { DatasetViewer } from './components/DatasetViewer';
import { DatasetFormatPanel } from './components/DatasetFormatPanel';
import { EvalReportsPanel } from './components/EvalReportsPanel';
import { LeaderboardPanel } from './components/LeaderboardPanel';
import { UnityDeployPanel } from './components/UnityDeployPanel';
import { RemoteConfigPanel } from './components/RemoteConfigPanel';

export default function App() {
  const [activeTab, setActiveTab] = useState<'overview' | 'training' | 'datasets' | 'dataset_params' | 'compare' | 'analytics' | 'commands'>('overview');
  const [logs, setLogs] = useState<string[]>([]);
  const [analyticsData, setAnalyticsData] = useState<Array<{ step: number; loss: number; acc: number; lr: number }>>([]);
  const [tensorBoardData, setTensorBoardData] = useState<TensorBoardData | null>(null);
  const [tbIsFallback, setTbIsFallback] = useState(false);
  const [uiError, setUiError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const fetchInFlightRef = useRef(false);
  const [commandModalOpen, setCommandModalOpen] = useState(false);
  const [selectedCommand, setSelectedCommand] = useState<string | null>(null);
  const [commandPayload, setCommandPayload] = useState<any>({});
  const [selectedJobForLogs, setSelectedJobForLogs] = useState<Job | null>(null);

  const [datasetViewNpc, setDatasetViewNpc] = useState<string>('');
  const [datasetViewTechnique, setDatasetViewTechnique] = useState<string>('');
  const [availableTechniques, setAvailableTechniques] = useState<Array<{ name: string; train_count: number; val_count: number }>>([]);
  const [serverPid, setServerPid] = useState<number>(0);
  const [presets, setPresets] = useState<Array<{ name: string; description: string }>>([]);
  const [presetDesc, setPresetDesc] = useState<Record<string, string>>({});

  const [trainingConfig, setTrainingConfig] = useState<TrainingConfig>({
    spec: 'subjects/chemistry_instructor.json',
    preset: 'fast-3b',
    learningRate: '2e-4',
    scheduler: 'cosine',
    batchSize: 4,
    epochs: 3,
    rank: 16,
    alpha: 32,
    baseModel: 'unsloth/Llama-3.2-3B-Instruct-bnb-4bit',
    wandb: false,
    technique: 'notebooklm',
  });

  const {
    jobs,
    selectedJobId,
    setSelectedJobId,
    selectedJobIds,
    setSelectedJobIds,
    activeFilter,
    setActiveFilter,
    filteredJobs,
    jobTypeFilter,
    toggleJobTypeFilter,
    stopJob,
    deleteJob,
    toggleJobSelection,
    exportJobsCsv,
    fetchJobs,
  } = useJobs();

  const {
    status,
    health,
    fetchStatus,
    toggleExecutionMode,
  } = useSystemStatus();

  const {
    telemetry,
    setTelemetry,
    fetchTelemetry,
  } = useTelemetry();

  const {
    datasets,
    subjects,
    runs,
    exportArtifacts,
    availableCommands,
    commandSchemas,
    fetchDatasets,
  } = useDatasets();
  const datasetsRef = useRef(datasets);

  const { connectionQuality } = useWebSocket({
    onTelemetry: (data) => setTelemetry(data),
    onJobUpdate: () => fetchJobs(),
    onFallbackPolling: () => { /* polling already runs every 5s */ },
    onResync: () => {
      fetchJobs();
      fetchStatus();
    },
  });

  // --- Data Fetching ---

  useEffect(() => {
    datasetsRef.current = datasets;
  }, [datasets]);

  const fetchData = async (showLoading = false) => {
    if (fetchInFlightRef.current) return;  // prevent overlapping fetches
    fetchInFlightRef.current = true;
    if (showLoading) setIsLoading(true);
    try {
      await Promise.all([
        fetchJobs(),
        fetchStatus(),
        fetchTelemetry(),
        fetchDatasets(),
        (async () => {
          const logsData = await fetchJson<string[]>('/api/logs');
          setLogs(logsData);
        })(),
        (async () => {
          try {
            const healthData = await fetchJson<HealthCheck>('/api/health');
            setServerPid(healthData.processId);
          } catch {}
        })(),
        (async () => {
          try {
            let presetsData: Array<{ name: string; description: string }> = [];
            try {
              presetsData = await fetchJson<Array<{ name: string; description: string }>>('/api/presets');
            } catch {
              presetsData = await fetchJson<Array<{ name: string; description: string }>>('/api/config/presets');
            }
            setPresets(presetsData);
            const descMap: Record<string, string> = {};
            for (const p of presetsData) descMap[p.name] = p.description;
            setPresetDesc(descMap);
          } catch {}
        })(),
      ]);
      setUiError(null);
    } catch (error) {
      setUiError(error instanceof Error ? error.message : 'Failed to fetch data');
    } finally {
      fetchInFlightRef.current = false;
      if (showLoading) setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchData(true);
    const interval = setInterval(fetchData, 5000);

    const handleNavigate = (e: Event) => {
      const detail = (e as CustomEvent).detail as { tab: string; npcKey?: string; technique?: string };
      if (detail.tab === 'datasets' && detail.npcKey) {
        const targetDataset = datasetsRef.current.find((dataset) => dataset.id === detail.npcKey);
        const targetTechnique = detail.technique || targetDataset?.versions[0]?.tag || '';
        setDatasetViewNpc(detail.npcKey);
        setDatasetViewTechnique(targetTechnique);
        setAvailableTechniques(targetDataset?.versions.map((version) => ({ name: version.tag, train_count: version.entries, val_count: 0 })) || []);
      }
      setActiveTab(detail.tab as any);
    };
    window.addEventListener('navigate-tab', handleNavigate);

    return () => {
      clearInterval(interval);
      window.removeEventListener('navigate-tab', handleNavigate);
    };
  }, []);

  useEffect(() => {
    const targetJobId = selectedJobId || jobs[0]?.id;
    if (!targetJobId) {
      setTensorBoardData(null);
      setTbIsFallback(true);
      fetchJson<Array<{ step: number; loss: number; acc: number; lr: number }>>('/api/analytics')
        .then(setAnalyticsData)
        .catch(() => setAnalyticsData([]));
      return;
    }

    fetchJson<TensorBoardData>(`/api/tensorboard?runId=${encodeURIComponent(targetJobId)}`)
      .then((tbData) => {
        if (tbData.error || Object.keys(tbData.scalars).length === 0) {
          setTbIsFallback(true);
          return fetchJson<Array<{ step: number; loss: number; acc: number; lr: number }>>('/api/analytics')
            .then(setAnalyticsData)
            .catch(() => setAnalyticsData([]));
        }
        setTbIsFallback(false);
        const lossScalars = tbData.scalars['train/loss'] || tbData.scalars['loss'] || [];
        const accScalars = tbData.scalars['eval/acc'] || tbData.scalars['acc'] || [];
        const lrScalars = tbData.scalars['train/learning_rate'] || tbData.scalars['learning_rate'] || [];

        const maxSteps = Math.max(
          lossScalars.length, accScalars.length, lrScalars.length, 1
        );
        const combined = Array.from({ length: maxSteps }, (_, i) => ({
          step: lossScalars[i]?.step || accScalars[i]?.step || lrScalars[i]?.step || i + 1,
          loss: lossScalars[i]?.value ?? 0,
          acc: accScalars[i]?.value ?? 0,
          lr: lrScalars[i]?.value ?? 0,
        }));
        setAnalyticsData(combined);
        setTensorBoardData(tbData);
      })
      .catch(() => {
        setTbIsFallback(true);
        fetchJson<Array<{ step: number; loss: number; acc: number; lr: number }>>('/api/analytics')
          .then(setAnalyticsData)
          .catch(() => setAnalyticsData([]));
      });
  }, [selectedJobId, jobs]);

  // --- Handlers ---

  const stopAllJobs = async () => {
    const runningJobs = jobs.filter((job) => job.status === 'running');
    if (runningJobs.length === 0) {
      setUiError('No running jobs to stop.');
      return;
    }
    setIsLoading(true);
    try {
      const stopResults = await Promise.all(runningJobs.map(async (job) => {
        const response = await fetch('/api/commands/stop', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: job.id }),
        });
        if (response.ok) return { id: job.id, ok: true, message: '' };
        const payload = await response.json().catch(() => ({}));
        return { id: job.id, ok: false, message: payload.error || response.statusText };
      }));
      const failures = stopResults.filter((result) => !result.ok);
      if (failures.length > 0) {
        setUiError(`Failed to stop ${failures.length} job(s): ${failures.map((failure) => `${failure.id} (${failure.message})`).join(', ')}`);
      }
      await fetchData(true);
    } catch (error) {
      setUiError(error instanceof Error ? error.message : 'Failed to stop running jobs');
    } finally {
      setIsLoading(false);
    }
  };

  const handleToggleExecutionMode = async () => {
    try {
      if (status?.executionMode === 'local') {
        const confirmed = window.confirm('Remote runner is not implemented yet. Remote command starts return 501. Switch anyway for configuration testing?');
        if (!confirmed) return;
      }
      await toggleExecutionMode();
      setUiError(status?.executionMode === 'local' ? 'Remote mode selected for configuration only. Remote runner is not implemented; command starts are blocked.' : null);
    } catch (error) {
      setUiError(error instanceof Error ? error.message : 'Failed to toggle execution mode');
    }
  };

  const triggerCommand = async (payload: Record<string, unknown>) => {
    if (status?.executionMode === 'remote') {
      throw new Error('Remote runner is not implemented yet. Switch Execution Mode back to Local before starting commands.');
    }

    const response = await fetch('/api/commands/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!response.ok) {
      const err = await response.json().catch(() => ({}));
      throw new Error(err.error || 'Failed to start command');
    }
    await fetchData(true);
  };

  const setNestedValue = (obj: Record<string, unknown>, dottedPath: string, rawValue: unknown): Record<string, unknown> => {
    const next: Record<string, unknown> = { ...obj };
    const parts = dottedPath.split('.');
    let cur: Record<string, unknown> = next;

    for (let i = 0; i < parts.length - 1; i += 1) {
      const part = parts[i];
      const existing = cur[part];
      if (typeof existing === 'object' && existing !== null && !Array.isArray(existing)) {
        cur[part] = { ...(existing as Record<string, unknown>) };
      } else {
        cur[part] = {};
      }
      cur = cur[part] as Record<string, unknown>;
    }

    cur[parts[parts.length - 1]] = rawValue;
    return next;
  };

  const getNestedValue = (obj: Record<string, unknown>, dottedPath: string): unknown => {
    return dottedPath.split('.').reduce<unknown>((acc, key) => {
      if (acc && typeof acc === 'object' && key in (acc as Record<string, unknown>)) {
        return (acc as Record<string, unknown>)[key];
      }
      return undefined;
    }, obj);
  };

  const getDefaultPayloadForCommand = (commandId: string): Record<string, unknown> => {
    const schema = commandSchemas[commandId]?.fields as Record<string, { default?: unknown }> | undefined;
    if (schema) {
      let payload: Record<string, unknown> = {};
      for (const [fieldPath, config] of Object.entries(schema)) {
        if (config.default !== undefined) {
          payload = setNestedValue(payload, fieldPath, config.default);
        }
      }
      if (!payload.commandId) payload.commandId = commandId;
      return payload;
    }

    const derivedNpcKey = trainingConfig.spec.replace('subjects/', '').replace('.json', '');
    switch (commandId) {
      case 'dataset-generate':
        return { spec: trainingConfig.spec, options: { technique: trainingConfig.technique, modelId: trainingConfig.baseModel } };
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

  const handleStopJob = async (id: string) => {
    try {
      await stopJob(id);
      await fetchData(true);
    } catch (error) {
      setUiError(error instanceof Error ? error.message : 'Failed to stop job');
    }
  };

  const handleDeleteJob = async (id: string) => {
    try {
      await deleteJob(id);
      if (selectedJobId === id) setSelectedJobId(null);
      setSelectedJobIds(prev => prev.filter(jId => jId !== id));
      await fetchData(true);
    } catch (error) {
      setUiError(error instanceof Error ? error.message : 'Failed to clear job');
    }
  };

  const handleSelectJob = (id: string) => {
    setSelectedJobId(id);
  };

  const handleSetActiveFilter = () => {
    setActiveFilter((prev) => (prev === 'all' ? 'running' : 'all'));
  };

  const handleOpenComparison = () => {
    setActiveTab('compare');
  };

  const handleManageJob = (id: string) => {
    setSelectedJobId(id);
    setSelectedJobIds((prev) => (prev.includes(id) ? prev : [...prev, id]));
    setActiveTab('compare');
  };

  const handleLaunchTraining = async () => {
    try {
      await triggerCommand({
        commandId: 'train',
        type: 'Training',
        spec: trainingConfig.spec,
        preset: trainingConfig.preset,
        options: {
          wandb: trainingConfig.wandb ? 'true' : 'false',
          learningRate: trainingConfig.learningRate,
          scheduler: trainingConfig.scheduler,
          batchSize: trainingConfig.batchSize,
          epochs: trainingConfig.epochs,
          rank: trainingConfig.rank,
          alpha: trainingConfig.alpha,
          baseModel: trainingConfig.baseModel,
          technique: trainingConfig.technique,
        },
      });
      setActiveTab('overview');
    } catch (error) {
      setUiError(error instanceof Error ? error.message : 'Training launch failed');
    }
  };

  const handleGenerateDataset = async () => {
    try {
      await triggerCommand({ commandId: 'dataset-generate', type: 'Dataset', spec: trainingConfig.spec, options: { technique: trainingConfig.technique, modelId: trainingConfig.baseModel } });
    } catch (error) {
      setUiError(error instanceof Error ? error.message : 'Dataset generation failed');
    }
  };

  const handleViewDataset = (npcKey: string, technique: string) => {
    if (!npcKey || !technique) return;
    setDatasetViewNpc(npcKey);
    setDatasetViewTechnique(technique);
    // Extract techniques from datasets state
    const ds = datasets.find((d) => d.id === npcKey);
    if (ds) {
      setAvailableTechniques(
        ds.versions.map((v) => ({ name: v.tag, train_count: v.entries, val_count: 0 }))
      );
    }
  };

  const handlePrepareTrainingFromDataset = (npcKey: string, technique: string) => {
    if (!npcKey || !technique) return;
    setTrainingConfig((prev) => ({
      ...prev,
      spec: `subjects/${npcKey}.json`,
      technique,
    }));
    setUiError(`Training Suite preselected for ${npcKey} using ${technique}. Review settings, then launch training.`);
    setActiveTab('training');
  };

  const handleClearSelection = () => {
    setSelectedJobIds([]);
  };

  const triggerCommandFromSystemHub = async (cmd: AvailableCommand) => {
    const payload = {
      commandId: cmd.id,
      type: cmd.type,
      ...getDefaultPayloadForCommand(cmd.id),
    };
    setSelectedCommand(cmd.id);
    setCommandPayload(payload);
    setCommandModalOpen(true);
  };

  const handleUpdateTrainingConfig = (config: Partial<TrainingConfig>) => {
    setTrainingConfig((prev) => ({ ...prev, ...config }));
  };

  const handleRightSidebarLaunchTraining = async () => {
    try {
      await triggerCommand({
        commandId: 'train',
        type: 'Training',
        spec: trainingConfig.spec,
        preset: trainingConfig.preset,
        options: {
          model: trainingConfig.baseModel,
          wandb: trainingConfig.wandb ? 'true' : 'false',
          learningRate: trainingConfig.learningRate,
          scheduler: trainingConfig.scheduler,
          batchSize: trainingConfig.batchSize,
          epochs: trainingConfig.epochs,
          rank: trainingConfig.rank,
          alpha: trainingConfig.alpha,
          technique: trainingConfig.technique,
        },
      });
    } catch (error) {
      setUiError(error instanceof Error ? error.message : 'Training start failed');
    }
  };

  const handleRightSidebarExport = async () => {
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
  };

  const handleRightSidebarGenerateDataset = async () => {
    try {
      await triggerCommand({ commandId: 'dataset-generate', type: 'Dataset', spec: trainingConfig.spec, options: { technique: trainingConfig.technique, modelId: trainingConfig.baseModel } });
    } catch (error) {
      setUiError(error instanceof Error ? error.message : 'Dataset generation failed');
    }
  };

  const handleSystemHubCommand = async (cmd: AvailableCommand) => {
    try {
      await triggerCommandFromSystemHub(cmd);
    } catch (error) {
      setUiError(error instanceof Error ? error.message : 'Command failed');
    }
  };

  const validateCommandPayload = (commandId: string, payload: Record<string, unknown>): string[] => {
    const fields = commandSchemas[commandId]?.fields as Record<string, { required?: boolean }> | undefined;
    if (!fields) return [];

    const missing: string[] = [];
    for (const [path, schema] of Object.entries(fields)) {
      if (!schema?.required || path === 'commandId') continue;
      const value = getNestedValue(payload, path);
      if (value === undefined || value === null || (typeof value === 'string' && value.trim() === '')) {
        missing.push(path);
      }
    }
    return missing;
  };

  const handleSetCommandPayload = (field: string, value: string) => {
    const selectedSchema = selectedCommand ? commandSchemas[selectedCommand]?.fields?.[field] : undefined;

    let typedValue: unknown = value;
    if (selectedSchema?.type === 'number') {
      const n = Number(value);
      typedValue = Number.isFinite(n) ? n : value;
    } else if (selectedSchema?.type === 'boolean') {
      typedValue = value === 'true';
    }

    setCommandPayload((prev: Record<string, unknown>) => setNestedValue(prev, field, typedValue));
  };

  const localModel = status?.localModel;
  const isLocalModelLoaded = Boolean(localModel?.loaded);
  const localModelLabel = localModel?.displayName || 'none loaded';
  const localModelSource = localModel?.source && localModel.source !== 'none' ? localModel.source : 'idle';
  const isRemoteMode = status?.executionMode === 'remote';
  const healthLabel = health ? (health.ok ? 'Health OK' : 'Health Degraded') : 'Health Unknown';
  const healthColorClass = health ? (health.ok ? 'text-success' : 'text-danger') : 'text-ink/40';
  const healthDotClass = health ? (health.ok ? 'bg-success' : 'bg-danger') : 'bg-ink/40';
  const selectedJobLogLines = selectedJobForLogs
    ? [
        ...(selectedJobForLogs.logs || []),
        ...selectedJobForLogs.stages.flatMap((stage) => stage.logs.map((line) => `[${stage.name}] ${line}`)),
      ]
    : [];

  return (
    <div className="flex flex-col h-screen overflow-hidden bg-bg text-ink font-sans border border-line selection:bg-accent/30 selection:text-ink-bright">
      {/* Top Global Monitor */}
      <header className="h-12 border-b border-line bg-header/80 backdrop-blur-xl flex items-center justify-between px-4 shrink-0 z-50">
        <div className="flex items-center gap-6">
          <div className="flex items-center gap-2 group cursor-pointer">
            <div className="w-2 h-2 rounded-full bg-accent glow-blue group-hover:scale-125 transition-transform"></div>
            <span className="font-mono text-xs font-bold tracking-widest uppercase gradient-text">Unsloth_Core v2.4</span>
          </div>
          <div className="h-4 w-px bg-line/50"></div>
          <div className="flex gap-6">
            <div className="flex flex-col">
              <span className="text-[8px] uppercase opacity-40 font-bold tracking-widest">GPU_NODE</span>
              <span className={cn("text-[10px] font-mono font-bold tracking-tight", telemetry && telemetry.gpuLoad > 90 ? "text-danger" : "text-accent")}>
                {telemetry ? `${telemetry.gpuName.split(' ')[0]} / ${telemetry.gpuLoad}%` : '---'}
              </span>
            </div>
            <div className="flex flex-col">
              <span className="text-[8px] uppercase opacity-40 font-bold tracking-widest">CPU_LOAD</span>
              <span className={cn("text-[10px] font-mono font-bold", telemetry && telemetry.cpuLoad > 75 ? "text-danger" : "text-success")}>{telemetry ? `${telemetry.cpuLoad}%` : '---'}</span>
            </div>
            <div className="flex flex-col min-w-[150px] max-w-[220px]">
              <span className="text-[8px] uppercase opacity-40 font-bold tracking-widest">LOCAL INFERENCE / ASSISTANT</span>
              <span
                title={isLocalModelLoaded ? `${localModelLabel} (${localModelSource === 'ollama' ? 'Ollama assistant model' : 'local inference model'})` : 'No Ollama assistant or llama-server inference model detected'}
                className={cn(
                  "text-[10px] font-mono font-bold truncate rounded-sm border px-1.5 py-0.5",
                  isLocalModelLoaded
                    ? "text-accent border-accent/30 bg-accent/10 shadow-[0_0_16px_rgba(81,226,255,0.08)]"
                    : "text-ink/35 border-line/60 bg-surface/40",
                )}
              >
                {isLocalModelLoaded ? `${localModelLabel} · ${localModelSource === 'ollama' ? 'Ollama assistant' : localModelSource}` : localModelLabel}
              </span>
            </div>
          </div>
        </div>
        <div className="flex items-center gap-4">
          <div className="flex flex-col text-right">
            <span className="text-[8px] uppercase opacity-40 font-bold tracking-widest">NETWORK_IO</span>
            <span className="text-[10px] font-mono font-bold text-ink/60">{telemetry ? `${telemetry.networkRxMBps.toFixed(1)}MB/s` : '---'}</span>
          </div>
          <div className="h-8 w-px bg-line/50" />
          <button onClick={stopAllJobs} className="px-3 py-1 bg-danger/10 text-danger border border-danger/30 text-[9px] font-bold rounded-sm uppercase tracking-wider hover:bg-danger/30 transition-all active:scale-95 shadow-lg shadow-danger/5">
            Emergency Kill
          </button>
        </div>
      </header>

      <div className="flex flex-1 overflow-hidden relative">
        {/* Background Mesh Overlay */}
        <div className="absolute inset-0 pointer-events-none opacity-20 bg-[radial-gradient(circle_at_50%_-20%,var(--accent-glow),transparent_50%)]" />

        {/* Left Sidebar: Assistant/Docs */}
        <AIAssistant />

        {/* Main Content: Matrix & Logs */}
        <main className="flex-1 flex flex-col overflow-hidden bg-bg">
          {/* Tab Selection */}
          <div className="flex px-4 border-b border-line bg-surface/30 backdrop-blur-md">
            {[
              { id: 'overview', label: 'Operations Matrix' },
              { id: 'datasets', label: 'Dataset Factory' },
              { id: 'dataset_params', label: 'Generation Specs' },
              { id: 'training', label: 'Training Suite' },
              { id: 'analytics', label: 'TensorBoard' },
              { id: 'commands', label: 'System Hub' },
              { id: 'compare', label: 'Model Comparison' },
            ].map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id as any)}
                className={cn(
                  "px-4 py-3 text-[9px] font-bold uppercase tracking-[0.2em] border-b-2 transition-all duration-300 relative group",
                  activeTab === tab.id ? "border-accent text-ink-bright" : "border-transparent text-ink/30 hover:text-ink/60",
                )}
              >
                {tab.label}
                {tab.id === 'compare' && selectedJobIds.length > 0 && (
                  <span className="ml-2 bg-accent text-bg px-1.5 rounded-full text-[8px] font-mono animate-pulse">
                    {selectedJobIds.length}
                  </span>
                )}
                {activeTab === tab.id && (
                  <motion.div layoutId="activeTab" className="absolute inset-0 bg-accent/5 -z-10" />
                )}
                <div className="absolute bottom-0 left-0 w-0 h-[2px] bg-accent transition-all duration-300 group-hover:w-full" />
              </button>
            ))}
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
                <div className="p-4 pb-0">
                  <NpcOverview
                    subjects={subjects}
                    datasets={datasets}
                    runs={runs}
                    exportArtifacts={exportArtifacts}
                    jobs={jobs}
                  />
                  <div className="h-px bg-line/50 mb-3" />
                </div>
                <OperationsMatrix
                  jobs={jobs}
                  filteredJobs={filteredJobs}
                  selectedJobIds={selectedJobIds}
                  selectedJobId={selectedJobId}
                  activeFilter={activeFilter}
                  jobTypeFilter={jobTypeFilter}
                  onSelectJob={handleSelectJob}
                  onToggleJobSelection={toggleJobSelection}
                  onSetActiveFilter={handleSetActiveFilter}
                  onToggleJobTypeFilter={toggleJobTypeFilter}
                  onStopJob={handleStopJob}
                  onExportCsv={exportJobsCsv}
                  onOpenComparison={handleOpenComparison}
                  onManageJob={handleManageJob}
                  onDeleteJob={handleDeleteJob}
                  onViewLogs={(job) => setSelectedJobForLogs(job)}
                />
              </motion.div>
            )}

            {activeTab === 'training' && (
              <TrainingSuite
                subjects={subjects}
                presets={presets}
                presetDesc={presetDesc}
                trainingConfig={trainingConfig}
                onUpdateTrainingConfig={handleUpdateTrainingConfig}
                onLaunchTraining={handleLaunchTraining}
              />
            )}

            {activeTab === 'analytics' && (
              <TensorBoardPanel
                data={analyticsData}
                onRefresh={fetchData}
                isLive={connectionQuality === 'connected'}
                isFallback={tbIsFallback}
              />
            )}

            {activeTab === 'commands' && (
              <div className="flex-1 flex flex-col overflow-hidden">
                <div className="flex-1 overflow-auto">
                  <SystemHub
                    availableCommands={availableCommands}
                    onTriggerCommand={handleSystemHubCommand}
                  />
                </div>
                <div className="border-t border-line p-4">
                  <details>
                    <summary className="text-[10px] font-bold text-ink/40 uppercase tracking-widest cursor-pointer hover:text-ink/60">
                      Evaluation Reports
                    </summary>
                    <div className="mt-3">
                      <EvalReportsPanel />
                    </div>
                    </details>
                  <div className="border-t border-line my-3" />
                  <details>
                    <summary className="text-[10px] font-bold text-ink/40 uppercase tracking-widest cursor-pointer hover:text-ink/60">
                      Supabase Leaderboard
                    </summary>
                    <div className="mt-3">
                      <LeaderboardPanel />
                    </div>
                  </details>

                  <div className="border-t border-line my-3" />
                  <details>
                    <summary className="text-[10px] font-bold text-ink/40 uppercase tracking-widest cursor-pointer hover:text-ink/60">
                      Unity Deployment
                    </summary>
                    <div className="mt-3">
                      <UnityDeployPanel />
                    </div>
                  </details>

                  <div className="border-t border-line my-3" />
                  <details>
                    <summary className="text-[10px] font-bold text-ink/40 uppercase tracking-widest cursor-pointer hover:text-ink/60">
                      Remote Configuration
                    </summary>
                    <div className="mt-3">
                      <RemoteConfigPanel />
                    </div>
                  </details>
                </div>
              </div>
            )}

            {activeTab === 'compare' && (
              <ModelComparison
                selectedJobIds={selectedJobIds}
                jobs={jobs}
                runs={runs}
                exportArtifacts={exportArtifacts}
                onToggleJobSelection={toggleJobSelection}
                onClearSelection={handleClearSelection}
                onNavigateTo={setActiveTab}
              />
            )}

            {activeTab === 'dataset_params' && (
              <DatasetFormatPanel
                subjects={subjects}
                datasets={datasets}
                trainingConfig={trainingConfig}
              />
            )}

            {activeTab === 'datasets' && (
              <div className="flex-1 flex flex-col overflow-hidden">
                <div className="flex-1 overflow-auto">
                  <DatasetFactory
                    datasets={datasets}
                    runs={runs}
                    exportArtifacts={exportArtifacts}
                    trainingConfig={trainingConfig}
                    onGenerateDataset={handleGenerateDataset}
                    onSelectDataset={handleViewDataset}
                    onPrepareTraining={handlePrepareTrainingFromDataset}
                  />
                </div>
                {/* Dataset viewer controls */}
                <div className="p-4 border-t border-line">
                  <div className="flex gap-2 items-center">
                    <select
                      value={datasetViewNpc}
                      onChange={(e) => { setDatasetViewNpc(e.target.value); setDatasetViewTechnique(''); }}
                      className="bg-bg border border-line text-[10px] rounded px-2 py-1 min-w-[140px]"
                    >
                      <option value="">Select NPC...</option>
                      {datasets.map((ds) => (
                        <option key={ds.id} value={ds.id}>{ds.name}</option>
                      ))}
                    </select>
                    <select
                      value={datasetViewTechnique}
                      onChange={(e) => setDatasetViewTechnique(e.target.value)}
                      className="bg-bg border border-line text-[10px] rounded px-2 py-1 min-w-[120px]"
                    >
                      <option value="">Technique...</option>
                      {datasets.find((d) => d.id === datasetViewNpc)?.versions.map((v) => (
                        <option key={v.tag} value={v.tag}>{v.tag} ({v.entries} entries)</option>
                      ))}
                    </select>
                    <button
                      onClick={() => handleViewDataset(datasetViewNpc, datasetViewTechnique)}
                      disabled={!datasetViewNpc || !datasetViewTechnique}
                      className="px-3 py-1 bg-accent text-bg text-[10px] font-bold rounded disabled:opacity-40 hover:bg-accent/80 transition-colors"
                    >
                      View Samples
                    </button>
                  </div>
                </div>
                {/* Dataset viewer results */}
                {datasetViewNpc && datasetViewTechnique && (
                  <div className="px-4 pb-4 max-h-[400px] overflow-auto">
                    <DatasetViewer npcKey={datasetViewNpc} technique={datasetViewTechnique} />
                  </div>
                )}
              </div>
            )}
          </AnimatePresence>

          {/* Logs Section */}
          <section className="h-52 border-t border-line bg-bg p-3 overflow-hidden flex flex-col group">
            <div className="flex justify-between items-center mb-2">
              <span className="text-[10px] font-bold text-ink/40 uppercase tracking-widest">Real-time Log Streams</span>
              <div className="flex gap-2 text-[9px] font-mono text-ink/30">
                <span>PID: {serverPid}</span>
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
                    log.includes('[DEBUG]') ? "text-warning" : "text-ink/60",
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
                  onClick={handleRightSidebarGenerateDataset}
                  disabled={isRemoteMode}
                  title={isRemoteMode ? 'Remote runner is not implemented. Switch to Local to start commands.' : 'Run dataset generation locally'}
                  className="w-full py-2 bg-accent hover:bg-accent/80 text-bg rounded-sm text-[11px] font-bold uppercase transition-all active:scale-95 shadow-lg shadow-accent/20 disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  Run Dataset Generator
                </button>
                <button
                  onClick={handleRightSidebarLaunchTraining}
                  disabled={isRemoteMode}
                  title={isRemoteMode ? 'Remote runner is not implemented. Switch to Local to start commands.' : 'Start LoRA training locally'}
                  className="w-full py-2 bg-panel border border-line hover:border-accent text-ink rounded-sm text-[11px] font-bold uppercase transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  Initialize LoRA Train
                </button>
                <button
                  onClick={handleRightSidebarExport}
                  disabled={isRemoteMode}
                  title={isRemoteMode ? 'Remote runner is not implemented. Switch to Local to start commands.' : 'Export locally for Unity'}
                  className="w-full py-2 bg-panel border border-line hover:border-accent text-ink rounded-sm text-[11px] font-bold uppercase transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  Export for Unity
                </button>
              </div>
            </div>

            <div>
              <h4 className="text-[10px] font-bold text-ink/40 uppercase tracking-widest mb-3">Dataset Versions</h4>
              <div className="space-y-2">
                {datasets.map((ds) => (
                  <div key={ds.id} className="p-2 bg-panel border border-line rounded flex flex-col gap-1">
                    <div className="flex justify-between items-center">
                      <span className="text-[10px] font-bold text-ink-bright truncate">{ds.name}</span>
                      <Shield className="w-3 h-3 text-success" />
                    </div>
                    <select className="bg-bg text-[10px] border border-line/30 rounded p-1 outline-none text-ink/60">
                      {ds.versions.map((v) => (
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
              <select
                value={trainingConfig.spec}
                onChange={(e) => setTrainingConfig({ ...trainingConfig, spec: e.target.value })}
                className="w-full bg-bg text-[10px] border border-line/30 rounded p-1.5 outline-none text-ink/60"
              >
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
                      <div className="text-[11px] font-bold flex flex-col gap-1">
                        <span>{status?.executionMode?.toUpperCase() || 'LOCAL'}</span>
                        {isRemoteMode && <span className="text-[8px] text-warning uppercase">Remote runner not implemented</span>}
                      </div>
                    </div>
                    <button
                      onClick={handleToggleExecutionMode}
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
                        health?.ok ? 'text-success' : 'text-danger',
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
            <div className={cn("w-1.5 h-1.5 rounded-full", healthDotClass)} />
            <span className={cn("font-bold", healthColorClass)}>{healthLabel}</span>
          </div>
          <span>Session: {status?.executionMode?.toUpperCase() || 'LOCAL'}</span>
          <span className="text-ink/20">©2026 NPC_GEN_CORE</span>
        </div>
      </footer>

      {/* Job Logs Drawer */}
      <AnimatePresence>
        {selectedJobForLogs && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 bg-black/55 z-50 flex justify-end"
            onClick={() => setSelectedJobForLogs(null)}
          >
            <motion.aside
              initial={{ x: 420 }}
              animate={{ x: 0 }}
              exit={{ x: 420 }}
              transition={{ type: 'spring', stiffness: 280, damping: 28 }}
              className="w-[420px] max-w-[92vw] h-full bg-surface border-l border-line shadow-2xl flex flex-col"
              onClick={(event) => event.stopPropagation()}
            >
              <div className="p-4 border-b border-line bg-header/80 flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="text-[9px] text-accent font-bold uppercase tracking-[0.2em]">Job Logs</div>
                  <h3 className="text-sm font-bold text-ink-bright truncate">{selectedJobForLogs.name}</h3>
                  <div className="text-[10px] text-ink/40 font-mono truncate">#{selectedJobForLogs.id}</div>
                </div>
                <button onClick={() => setSelectedJobForLogs(null)} className="text-ink/40 hover:text-ink transition-colors">
                  <XCircle className="w-5 h-5" />
                </button>
              </div>

              <div className="p-4 border-b border-line bg-bg/40 text-[10px] font-mono text-ink/50 space-y-1">
                <div>Status: <span className="text-ink-bright">{selectedJobForLogs.status}</span></div>
                <div>Type: <span className="text-ink-bright">{selectedJobForLogs.type}</span></div>
                {selectedJobForLogs.command && <div className="truncate">Command: <span className="text-accent">{selectedJobForLogs.command.join(' ')}</span></div>}
              </div>

              <div className="flex-1 overflow-y-auto custom-scrollbar bg-black/50 p-3 font-mono text-[10px] leading-relaxed">
                {selectedJobLogLines.length > 0 ? (
                  selectedJobLogLines.map((line, index) => (
                    <div key={`${index}-${line.slice(0, 20)}`} className={cn(
                      "py-0.5 border-b border-white/[0.03] whitespace-pre-wrap break-words",
                      line.includes('[STDERR]') || line.toLowerCase().includes('error') ? 'text-danger/90' : 'text-ink/70',
                    )}>
                      {line}
                    </div>
                  ))
                ) : (
                  <div className="h-full flex flex-col items-center justify-center text-center text-ink/35 gap-2">
                    <Terminal className="w-8 h-8 opacity-30" />
                    <div className="text-xs font-bold uppercase tracking-wider">No logs recorded</div>
                    <p className="max-w-xs text-[10px] leading-relaxed">This job has no stdout, stderr, or stage log lines in the job registry yet. Running jobs will stream logs here once output is captured.</p>
                  </div>
                )}
              </div>
            </motion.aside>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Command Modal */}
      <AnimatePresence>
        {commandModalOpen && selectedCommand && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 bg-black/50 flex items-center justify-center z-50"
            onClick={() => setCommandModalOpen(false)}
          >
            <motion.div
              initial={{ scale: 0.9, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.9, opacity: 0 }}
              className="bg-surface border border-line rounded-lg p-6 w-96 max-w-[90vw] max-h-[80vh] overflow-y-auto"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex justify-between items-center mb-4">
                <h3 className="text-lg font-bold text-ink-bright">Configure Command</h3>
                <button onClick={() => setCommandModalOpen(false)} className="text-ink/40 hover:text-ink">
                  <XCircle className="w-5 h-5" />
                </button>
              </div>

              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-bold text-ink/60 mb-2">Command ID</label>
                  <div className="p-2 bg-bg border border-line rounded text-sm font-mono">{selectedCommand}</div>
                </div>

                {(selectedCommand && commandSchemas[selectedCommand]?.fields
                  ? Object.entries(commandSchemas[selectedCommand].fields)
                      .filter(([field]) => field !== 'commandId' && field !== 'type')
                      .map(([field, schema]: [string, any]) => {
                        const rawValue = getNestedValue(commandPayload as Record<string, unknown>, field);
                        const value = rawValue === undefined || rawValue === null ? '' : String(rawValue);
                        return (
                          <div key={field}>
                            <label className="block text-sm font-bold text-ink/60 mb-2">
                              {field.replace(/\./g, ' → ').replace(/([A-Z])/g, ' $1')}
                              {schema?.required ? <span className="text-danger"> *</span> : null}
                            </label>
                            {Array.isArray(schema?.enum) && schema.enum.length > 0 ? (
                              <select
                                value={value}
                                onChange={(e) => handleSetCommandPayload(field, e.target.value)}
                                className="w-full p-2 bg-bg border border-line rounded text-sm focus:outline-none focus:border-accent"
                              >
                                {schema.enum.map((opt: string) => (
                                  <option key={opt} value={opt}>{opt}</option>
                                ))}
                              </select>
                            ) : schema?.type === 'boolean' ? (
                              <select
                                value={value || 'false'}
                                onChange={(e) => handleSetCommandPayload(field, e.target.value)}
                                className="w-full p-2 bg-bg border border-line rounded text-sm focus:outline-none focus:border-accent"
                              >
                                <option value="false">false</option>
                                <option value="true">true</option>
                              </select>
                            ) : (
                              <input
                                type={schema?.type === 'number' ? 'number' : 'text'}
                                value={value}
                                onChange={(e) => handleSetCommandPayload(field, e.target.value)}
                                className="w-full p-2 bg-bg border border-line rounded text-sm focus:outline-none focus:border-accent"
                              />
                            )}
                            {schema?.description ? (
                              <div className="text-[10px] text-ink/40 mt-1">{schema.description}</div>
                            ) : null}
                          </div>
                        );
                      })
                  : Object.keys(commandPayload)
                      .filter((key: string) => key !== 'commandId' && key !== 'type')
                      .map((field: string) => (
                        <div key={field}>
                          <label className="block text-sm font-bold text-ink/60 mb-2 capitalize">{field.replace(/([A-Z])/g, ' $1')}</label>
                          <input
                            type="text"
                            value={String((commandPayload as Record<string, unknown>)[field] || '')}
                            onChange={(e) => handleSetCommandPayload(field, e.target.value)}
                            className="w-full p-2 bg-bg border border-line rounded text-sm focus:outline-none focus:border-accent"
                          />
                        </div>
                      )))
                }

                <div className="flex gap-2 pt-4">
                  <button
                    onClick={async () => {
                      try {
                        const missing = validateCommandPayload(selectedCommand, commandPayload as Record<string, unknown>);
                        if (missing.length > 0) {
                          throw new Error(`Missing required fields: ${missing.join(', ')}`);
                        }
                        await triggerCommand(commandPayload);
                        setCommandModalOpen(false);
                        setSelectedCommand(null);
                        setCommandPayload({});
                      } catch (error) {
                        setUiError(error instanceof Error ? error.message : 'Command execution failed');
                      }
                    }}
                    className="flex-1 py-2 bg-accent text-bg rounded font-bold hover:bg-accent/80 transition-colors"
                  >
                    Execute Command
                  </button>
                  <button
                    onClick={() => {
                      setCommandModalOpen(false);
                      setSelectedCommand(null);
                      setCommandPayload({});
                    }}
                    className="px-4 py-2 bg-line/20 text-ink/60 rounded hover:bg-line/40 transition-colors"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
