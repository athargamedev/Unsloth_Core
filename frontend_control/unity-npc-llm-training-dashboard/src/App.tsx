import { useState, useEffect, useRef, lazy, Suspense } from 'react';
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
import { TrainingSuite } from './components/TrainingSuite';
import { SystemHub } from './components/SystemHub';
import { NpcOverview } from './components/NpcOverview';
import { Card } from './components/Card';

const DatasetFactory = lazy(() => import('./components/DatasetFactory').then((m) => ({ default: m.DatasetFactory })));
const TensorBoardPanel = lazy(() => import('./components/TensorBoardPanel').then((m) => ({ default: m.TensorBoardPanel })));
const ModelComparison = lazy(() => import('./components/ModelComparison').then((m) => ({ default: m.ModelComparison })));
const DatasetViewer = lazy(() => import('./components/DatasetViewer').then((m) => ({ default: m.DatasetViewer })));
const DatasetFormatPanel = lazy(() => import('./components/DatasetFormatPanel').then((m) => ({ default: m.DatasetFormatPanel })));
const EvalReportsPanel = lazy(() => import('./components/EvalReportsPanel').then((m) => ({ default: m.EvalReportsPanel })));
const LeaderboardPanel = lazy(() => import('./components/LeaderboardPanel').then((m) => ({ default: m.LeaderboardPanel })));
const UnityDeployPanel = lazy(() => import('./components/UnityDeployPanel').then((m) => ({ default: m.UnityDeployPanel })));
const RemoteConfigPanel = lazy(() => import('./components/RemoteConfigPanel').then((m) => ({ default: m.RemoteConfigPanel })));

export default function App() {
  const [activeTab, setActiveTab] = useState<'overview' | 'jobs' | 'training' | 'datasets' | 'dataset_params' | 'compare' | 'analytics' | 'commands' | 'logs'>('overview');
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
  const logsEndRef = useRef<HTMLDivElement>(null);

  const renderTabSkeleton = (variant: 'chart' | 'table' | 'form' | 'list') => (
    <div className="flex-1 p-4 space-y-3 animate-pulse">
      <div className="h-4 w-40 bg-line/60 rounded" />
      {variant === 'chart' && (
        <>
          <div className="h-48 bg-line/40 rounded" />
          <div className="grid grid-cols-3 gap-3">
            <div className="h-16 bg-line/30 rounded" />
            <div className="h-16 bg-line/30 rounded" />
            <div className="h-16 bg-line/30 rounded" />
          </div>
        </>
      )}
      {variant === 'table' && (
        <div className="space-y-2">
          {Array.from({ length: 6 }).map((_, idx) => (
            <div key={idx} className="h-10 bg-line/30 rounded" />
          ))}
        </div>
      )}
      {variant === 'form' && (
        <div className="grid grid-cols-2 gap-3">
          <div className="h-20 bg-line/30 rounded" />
          <div className="h-20 bg-line/30 rounded" />
          <div className="h-20 bg-line/30 rounded" />
          <div className="h-20 bg-line/30 rounded" />
        </div>
      )}
      {variant === 'list' && (
        <div className="space-y-2">
          <div className="h-24 bg-line/30 rounded" />
          <div className="h-24 bg-line/30 rounded" />
          <div className="h-24 bg-line/30 rounded" />
        </div>
      )}
    </div>
  );

  useEffect(() => {
    if (activeTab === 'logs' && logsEndRef.current) {
      logsEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [logs, activeTab]);

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
          } catch { }
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
          } catch { }
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
      const VALID_TABS = ['overview', 'training', 'datasets', 'dataset_params', 'compare', 'analytics', 'commands'] as const;
      type ValidTab = typeof VALID_TABS[number];
      if ((VALID_TABS as readonly string[]).includes(detail.tab)) {
        setActiveTab(detail.tab as ValidTab);
      }
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
      case 'init':
        return { npcKey: '', options: { subject: '', name: '' } };
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

  const handleInitNpc = () => {
    const cmd = availableCommands.find(c => c.id === 'init');
    if (cmd) {
      triggerCommandFromSystemHub(cmd);
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

  const handleQuickStartOpenPrepareData = () => {
    setActiveTab('dataset_params');
  };

  const handleQuickStartOpenTraining = () => {
    setActiveTab('training');
  };

  const handleQuickStartOpenEvaluate = () => {
    setActiveTab('analytics');
  };

  const handleQuickStartOpenDeployOps = () => {
    setActiveTab('jobs');
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
  const workflowStepByTab: Record<string, string> = {
    overview: 'Quick Start',
    dataset_params: 'Step 1 · Prepare Data',
    training: 'Step 2 · Train',
    analytics: 'Step 3 · Evaluate',
    jobs: 'Step 4 · Deploy/Run Ops',
    datasets: 'Dataset Browser',
    compare: 'Model Comparison',
    logs: 'System Console',
    commands: 'Advanced',
  };
  const activeWorkflowStep = workflowStepByTab[activeTab] || 'Quick Start';
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
          <div className="px-2 py-0.5 border border-accent/30 bg-accent/10 rounded text-[11px] text-accent font-semibold whitespace-nowrap">
            {activeWorkflowStep}
          </div>
          <div className="h-4 w-px bg-line/50"></div>
          <div className="flex gap-6">
            <div className="flex flex-col">
              <span className="text-[12px] uppercase opacity-40 font-bold tracking-widest">GPU_NODE</span>
              <span className={cn("text-[10px] font-mono font-bold tracking-tight", telemetry && telemetry.gpuLoad > 90 ? "text-danger" : "text-accent")}>
                {telemetry ? `${telemetry.gpuName.split(' ')[0]} / ${telemetry.gpuLoad}%` : '---'}
              </span>
            </div>
            <div className="flex flex-col">
              <span className="text-[12px] uppercase opacity-40 font-bold tracking-widest">CPU_LOAD</span>
              <span className={cn("text-[10px] font-mono font-bold", telemetry && telemetry.cpuLoad > 75 ? "text-danger" : "text-success")}>{telemetry ? `${telemetry.cpuLoad}%` : '---'}</span>
            </div>
            <div className="flex flex-col min-w-[150px] max-w-[220px]">
              <span className="text-[12px] uppercase opacity-40 font-bold tracking-widest">LOCAL INFERENCE / ASSISTANT</span>
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
            <span className="text-[12px] uppercase opacity-40 font-bold tracking-widest">NETWORK_IO</span>
            <span className="text-[10px] font-mono font-bold text-ink/60">{telemetry ? `${telemetry.networkRxMBps.toFixed(1)}MB/s` : '---'}</span>
          </div>
          <div className="h-8 w-px bg-line/50" />
          <button onClick={stopAllJobs} className="px-3 py-1 bg-danger/10 text-danger border border-danger/30 text-[12px] font-bold rounded-sm uppercase tracking-wider hover:bg-danger/30 transition-all active:scale-95 shadow-lg shadow-danger/5">
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
          <div className="flex px-4 border-b border-line bg-surface/30 backdrop-blur-md overflow-x-auto whitespace-nowrap no-scrollbar">
            {[
              { id: 'overview', label: 'Quick Start', shortLabel: 'Start' },
              { id: 'dataset_params', label: '1) Prepare Data', shortLabel: 'Data' },
              { id: 'training', label: '2) Train', shortLabel: 'Train' },
              { id: 'analytics', label: '3) Evaluate', shortLabel: 'Eval' },
              { id: 'jobs', label: '4) Deploy/Run Ops', shortLabel: 'Ops' },
              { id: 'datasets', label: 'Dataset Browser', shortLabel: 'Browser' },
              { id: 'compare', label: 'Model Comparison', shortLabel: 'Compare' },
              { id: 'logs', label: 'System Console', shortLabel: 'Console' },
              { id: 'commands', label: 'Advanced', shortLabel: 'Adv' },
            ].map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id as any)}
                className={cn(
                  "shrink-0 px-4 py-3 text-[12px] font-bold uppercase tracking-[0.12em] border-b-2 transition-all duration-300 relative group",
                  activeTab === tab.id ? "border-accent text-ink-bright" : "border-transparent text-ink/30 hover:text-ink/60",
                )}
              >
                <span className="sm:hidden">{tab.shortLabel}</span>
                <span className="hidden sm:inline">{tab.label}</span>
                {tab.id === 'compare' && selectedJobIds.length > 0 && (
                  <span className="ml-2 bg-accent text-bg px-1.5 rounded-full text-[12px] font-mono animate-pulse">
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
                className="flex-1 flex flex-col overflow-auto p-4 space-y-6 custom-scrollbar bg-bg/20"
              >
                <div className="flex justify-between items-end mb-2">
                  <div>
                    <h3 className="text-xs font-bold text-ink-bright uppercase tracking-widest">Project Infrastructure</h3>
                    <p className="text-[10px] text-ink/40">Real-time status of all NPC subjects and knowledge bases</p>
                  </div>
                  <div className="flex gap-4">
                    <div className="text-right">
                      <span className="block text-[12px] uppercase font-bold text-ink/30">Total Subjects</span>
                      <span className="text-lg font-bold text-accent">{subjects.length}</span>
                    </div>
                    <div className="text-right border-l border-line/30 pl-4">
                      <span className="block text-[12px] uppercase font-bold text-ink/30">Active Jobs</span>
                      <span className="text-lg font-bold text-success">{jobs.filter(j => j.status === 'running').length}</span>
                    </div>
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-3">
                  <button
                    onClick={handleQuickStartOpenPrepareData}
                    className="p-3 border border-accent/30 bg-accent/5 rounded-sm text-left hover:bg-accent/10 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/60"
                  >
                    <div className="text-[12px] font-bold text-accent uppercase tracking-wider">Step 1</div>
                    <div className="text-sm font-semibold text-ink-bright mt-1">Prepare Data</div>
                    <div className="text-[12px] text-ink/60 mt-1">Set spec + generation technique and launch dataset generation.</div>
                  </button>

                  <button
                    onClick={handleQuickStartOpenTraining}
                    className="p-3 border border-success/30 bg-success/5 rounded-sm text-left hover:bg-success/10 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-success/60"
                  >
                    <div className="text-[12px] font-bold text-success uppercase tracking-wider">Step 2</div>
                    <div className="text-sm font-semibold text-ink-bright mt-1">Train</div>
                    <div className="text-[12px] text-ink/60 mt-1">Review rank, alpha, base model and launch training.</div>
                  </button>

                  <button
                    onClick={handleQuickStartOpenEvaluate}
                    className="p-3 border border-warning/30 bg-warning/5 rounded-sm text-left hover:bg-warning/10 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-warning/60"
                  >
                    <div className="text-[12px] font-bold text-warning uppercase tracking-wider">Step 3</div>
                    <div className="text-sm font-semibold text-ink-bright mt-1">Evaluate</div>
                    <div className="text-[12px] text-ink/60 mt-1">Check TensorBoard curves and compare run quality.</div>
                  </button>

                  <button
                    onClick={handleQuickStartOpenDeployOps}
                    className="p-3 border border-line bg-surface rounded-sm text-left hover:bg-white/5 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/60"
                  >
                    <div className="text-[12px] font-bold text-ink/70 uppercase tracking-wider">Step 4</div>
                    <div className="text-sm font-semibold text-ink-bright mt-1">Deploy / Run Ops</div>
                    <div className="text-[12px] text-ink/60 mt-1">Track jobs, stop failures, open logs, and verify completion.</div>
                  </button>
                </div>

                <div className="flex flex-wrap gap-2 items-center">
                  <button
                    onClick={handleGenerateDataset}
                    className="px-3 py-1.5 bg-accent text-bg text-[12px] font-bold rounded-sm hover:brightness-110 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/60"
                  >
                    Run Step 1 Now
                  </button>
                  <button
                    onClick={handleLaunchTraining}
                    className="px-3 py-1.5 bg-success text-bg text-[12px] font-bold rounded-sm hover:brightness-110 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-success/60"
                  >
                    Run Step 2 Now
                  </button>
                  <button
                    onClick={() => setActiveTab('compare')}
                    className="px-3 py-1.5 bg-panel border border-line text-[12px] font-bold rounded-sm hover:bg-white/5 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/60"
                  >
                    Open Compare
                  </button>
                </div>

                <NpcOverview
                  subjects={subjects}
                  datasets={datasets}
                  runs={runs}
                  exportArtifacts={exportArtifacts}
                  jobs={jobs}
                />
              </motion.div>
            )}

            {activeTab === 'jobs' && (
              <motion.div
                key="jobs"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="flex-1 flex flex-col overflow-hidden"
              >
                <OperationsMatrix
                  jobs={jobs}
                  filteredJobs={filteredJobs}
                  selectedJobIds={selectedJobIds}
                  selectedJobId={selectedJobId}
                  activeFilter={activeFilter}
                  jobTypeFilter={jobTypeFilter}
                  isLoading={isLoading}
                  uiError={uiError}
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

            {activeTab === 'logs' && (
              <motion.div
                key="logs"
                initial={{ opacity: 0, scale: 0.98 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.98 }}
                className="flex-1 flex flex-col overflow-hidden bg-black/40"
              >
                <div className="p-3 border-b border-line bg-surface/30 flex justify-between items-center backdrop-blur-sm">
                  <div className="flex items-center gap-2">
                    <div className="w-2 h-2 rounded-full bg-accent animate-pulse" />
                    <span className="text-[10px] font-bold text-ink-bright uppercase tracking-widest">Global Telemetry Stream</span>
                  </div>
                  <div className="flex gap-3">
                    <span className="text-[12px] text-ink/40 font-mono">BUFFER: {logs.length} LINES</span>
                    <button
                      onClick={() => setLogs([])}
                      className="text-[12px] font-bold text-accent hover:brightness-125 uppercase tracking-tighter"
                    >
                      Reset Console
                    </button>
                  </div>
                </div>
                <div className="flex-1 overflow-auto p-4 font-mono text-[10px] space-y-0.5 custom-scrollbar bg-black/30 selection:bg-accent/30">
                  {logs.length > 0 ? (
                    logs.map((log, i) => {
                      // Clean up log lines for display
                      const cleanedLog = log
                        .replace(/^\[STDOUT\]\[[^\]]+\]\s*/, '')
                        .replace(/^\[STDERR\]\[[^\]]+\]\s*/, '⚠️ ')
                        .replace(/^\[SYSTEM\]\s*/, '⚙️ ');

                      return (
                        <div key={i} className="whitespace-pre-wrap break-all border-l border-line/5 pl-2 py-0.5 hover:bg-white/5 transition-colors group flex gap-3">
                          <span className="text-ink/10 select-none group-hover:text-ink/30 shrink-0 w-8">{(i + 1).toString().padStart(4, '0')}</span>
                          <span className={log.includes('[ERROR]') || log.includes('failed') ? 'text-danger' : log.includes('[STDERR]') ? 'text-warning/80' : log.includes('[SYSTEM]') ? 'text-accent' : 'text-ink/60'}>
                            {cleanedLog}
                          </span>
                        </div>
                      );
                    })
                  ) : (
                    <div className="h-full flex flex-col items-center justify-center space-y-2 opacity-20">
                      <div className="w-8 h-8 border-2 border-accent border-t-transparent rounded-full animate-spin" />
                      <div className="text-[10px] uppercase font-bold tracking-[0.2em]">Synchronizing Stream...</div>
                    </div>
                  )}
                  <div ref={logsEndRef} />
                </div>
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
              <Suspense fallback={renderTabSkeleton('chart')}>
                <TensorBoardPanel
                  data={analyticsData}
                  onRefresh={fetchData}
                  isLive={connectionQuality === 'connected'}
                  isFallback={tbIsFallback}
                />
              </Suspense>
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
                      <Suspense fallback={<div className="text-[12px] text-ink/50">Loading reports…</div>}>
                        <EvalReportsPanel />
                      </Suspense>
                    </div>
                  </details>
                  <div className="border-t border-line my-3" />
                  <details>
                    <summary className="text-[10px] font-bold text-ink/40 uppercase tracking-widest cursor-pointer hover:text-ink/60">
                      Supabase Leaderboard
                    </summary>
                    <div className="mt-3">
                      <Suspense fallback={<div className="text-[12px] text-ink/50">Loading leaderboard…</div>}>
                        <LeaderboardPanel />
                      </Suspense>
                    </div>
                  </details>

                  <div className="border-t border-line my-3" />
                  <details>
                    <summary className="text-[10px] font-bold text-ink/40 uppercase tracking-widest cursor-pointer hover:text-ink/60">
                      Unity Deployment
                    </summary>
                    <div className="mt-3">
                      <Suspense fallback={<div className="text-[12px] text-ink/50">Loading deployment panel…</div>}>
                        <UnityDeployPanel />
                      </Suspense>
                    </div>
                  </details>

                  <div className="border-t border-line my-3" />
                  <details>
                    <summary className="text-[10px] font-bold text-ink/40 uppercase tracking-widest cursor-pointer hover:text-ink/60">
                      Remote Configuration
                    </summary>
                    <div className="mt-3">
                      <Suspense fallback={<div className="text-[12px] text-ink/50">Loading remote config…</div>}>
                        <RemoteConfigPanel />
                      </Suspense>
                    </div>
                  </details>
                </div>
              </div>
            )}

            {activeTab === 'compare' && (
              <Suspense fallback={renderTabSkeleton('table')}>
                <ModelComparison
                  selectedJobIds={selectedJobIds}
                  jobs={jobs}
                  runs={runs}
                  exportArtifacts={exportArtifacts}
                  onToggleJobSelection={toggleJobSelection}
                  onClearSelection={handleClearSelection}
                  onNavigateTo={setActiveTab}
                />
              </Suspense>
            )}

            {activeTab === 'dataset_params' && (
              <Suspense fallback={renderTabSkeleton('form')}>
                <DatasetFormatPanel
                  subjects={subjects.map((s) => ({ ...s, name: s.id }))}
                  datasets={datasets}
                  trainingConfig={trainingConfig}
                  onGenerateDataset={(npcKey) => {
                    const cmd = availableCommands.find(c => c.id === 'dataset-generate');
                    if (cmd) {
                      const payload = {
                        commandId: cmd.id,
                        type: cmd.type,
                        spec: `subjects/${npcKey}.json`,
                        options: { technique: 'ollama' }
                      };
                      setSelectedCommand(cmd.id);
                      setCommandPayload(payload);
                      setCommandModalOpen(true);
                    }
                  }}
                />
              </Suspense>
            )}

            {activeTab === 'datasets' && (
              <Suspense fallback={renderTabSkeleton('list')}>
                <div className="flex-1 flex flex-col overflow-hidden">
                  <div className="flex-1 overflow-auto">
                    <DatasetFactory
                      datasets={datasets}
                      runs={runs}
                      exportArtifacts={exportArtifacts}
                      trainingConfig={trainingConfig}
                      onGenerateDataset={handleGenerateDataset}
                      onInitNpc={handleInitNpc}
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
                      <Suspense fallback={<div className="text-[12px] text-ink/50">Loading dataset samples…</div>}>
                        <DatasetViewer npcKey={datasetViewNpc} technique={datasetViewTechnique} />
                      </Suspense>
                    </div>
                  )}
                </div>
              </Suspense>
            )}
          </AnimatePresence>

          {/* Logs Section */}
          <section className="h-52 border-t border-line bg-bg p-3 overflow-hidden flex flex-col group">
            <div className="flex justify-between items-center mb-2">
              <span className="text-[10px] font-bold text-ink/40 uppercase tracking-widest">Real-time Log Streams</span>
              <div className="flex gap-2 text-[12px] font-mono text-ink/30">
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

        {/* Right Sidebar: Contextual Controls & Telemetry */}
        <aside className="w-64 border-l border-line bg-surface flex flex-col shrink-0 overflow-hidden backdrop-blur-xl">
          <div className="p-4 border-b border-line bg-accent/5">
            <div className="flex justify-between items-center mb-4">
              <h3 className="text-[10px] font-bold text-accent uppercase tracking-[0.2em]">Node Status</h3>
              <div className="flex items-center gap-1.5">
                <div className={`w-1.5 h-1.5 rounded-full ${connectionQuality === 'connected' ? 'bg-success animate-pulse' : 'bg-danger'}`} />
                <span className="text-[12px] font-bold text-ink/40 uppercase">{connectionQuality}</span>
              </div>
            </div>

            <div className="space-y-3">
              <div>
                <div className="flex justify-between text-[12px] mb-1">
                  <span className="text-ink/40 uppercase font-bold">GPU Load</span>
                  <span className="text-ink font-mono font-bold">{telemetry?.gpuLoad || 0}%</span>
                </div>
                <div className="h-1 w-full bg-line rounded-full overflow-hidden">
                  <div className="h-full bg-accent transition-all duration-500" style={{ width: `${telemetry?.gpuLoad || 0}%` }} />
                </div>
              </div>
              <div>
                <div className="flex justify-between text-[12px] mb-1">
                  <span className="text-ink/40 uppercase font-bold">Memory</span>
                  <span className="text-ink font-mono font-bold">{((telemetry?.memoryUsedGB || 0) / (telemetry?.memoryTotalGB || 1) * 100).toFixed(0)}%</span>
                </div>
                <div className="h-1 w-full bg-line rounded-full overflow-hidden">
                  <div className="h-full bg-ink/30" style={{ width: `${Math.min(100, (telemetry?.memoryUsedGB || 0) / (telemetry?.memoryTotalGB || 1) * 100)}%` }} />
                </div>
              </div>
            </div>
          </div>

          <div className="flex-1 overflow-auto custom-scrollbar p-4 space-y-6">
            {/* Quick Actions */}
            <details className="group" open>
              <summary className="flex justify-between items-center cursor-pointer list-none">
                <span className="text-[12px] font-bold text-ink/40 uppercase tracking-widest group-open:text-ink/60">Quick Actions</span>
                <span className="text-ink/20 group-open:rotate-180 transition-transform">▼</span>
              </summary>
              <div className="mt-4 space-y-2">
                <button
                  onClick={handleRightSidebarGenerateDataset}
                  disabled={isRemoteMode}
                  className="w-full py-1.5 bg-accent text-bg text-[10px] font-bold rounded-sm uppercase tracking-tighter hover:brightness-110 active:scale-95 transition-all shadow-lg shadow-accent/10 disabled:opacity-40"
                >
                  Generate Data
                </button>
                <button
                  onClick={handleRightSidebarLaunchTraining}
                  disabled={isRemoteMode}
                  className="w-full py-1.5 bg-surface border border-line text-ink text-[10px] font-bold rounded-sm uppercase tracking-tighter hover:bg-line/20 active:scale-95 transition-all disabled:opacity-40"
                >
                  Launch Train
                </button>
              </div>
            </details>

            {/* Model & Registry */}
            <details className="group">
              <summary className="flex justify-between items-center cursor-pointer list-none">
                <span className="text-[12px] font-bold text-ink/40 uppercase tracking-widest group-open:text-ink/60">Local Model</span>
                <span className="text-ink/20 group-open:rotate-180 transition-transform">▼</span>
              </summary>
              <div className="mt-4">
                <LocalModelPanel status={status?.localModel} />
              </div>
            </details>

            {/* Health Monitor */}
            <details className="group">
              <summary className="flex justify-between items-center cursor-pointer list-none">
                <span className="text-[12px] font-bold text-ink/40 uppercase tracking-widest group-open:text-ink/60">Registry Health</span>
                <span className="text-ink/20 group-open:rotate-180 transition-transform">▼</span>
              </summary>
              <div className="mt-4">
                <SystemStatusPanel status={health} />
              </div>
            </details>
          </div>

          <div className="p-4 bg-accent/5 border-t border-line">
            <div className="text-[12px] text-accent font-bold mb-1 flex items-center gap-1 uppercase tracking-tighter">
              <Zap className="w-2.5 h-2.5 fill-current" />
              Optimization Tip
            </div>
            <p className="text-[12px] leading-tight text-ink/60 italic">
              Adjust temperature to 0.4 for higher coherence in complex instruction sets.
            </p>
          </div>
        </aside>
      </div>

      {/* Footer Status Bar */}
      <footer className="h-6 bg-header border-t border-line px-4 flex items-center justify-between text-[12px] font-mono text-ink/40">
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
                  <div className="text-[12px] text-accent font-bold uppercase tracking-[0.2em]">Job Logs</div>
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
                    disabled={isRemoteMode}
                    title={isRemoteMode ? 'Remote runner is not implemented. Switch to Local before executing commands.' : 'Execute command locally'}
                    className="flex-1 py-2 bg-accent text-bg rounded font-bold hover:bg-accent/80 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    {isRemoteMode ? 'Remote Runner Unavailable' : 'Execute Command'}
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

// --- Sub-components for Sidebar ---

function LocalModelPanel({ status }: { status: any }) {
  if (!status) return <div className="text-[10px] text-ink/40 italic">No model status reported.</div>;

  return (
    <div className="space-y-2">
      <div className="flex justify-between items-center">
        <span className="text-[10px] text-ink/40">Model ID</span>
        <span className="text-[10px] font-mono text-accent truncate max-w-[100px]">{status.modelId || 'none'}</span>
      </div>
      <div className="flex justify-between items-center">
        <span className="text-[10px] text-ink/40">Status</span>
        <span className={`text-[12px] font-bold uppercase ${status.loaded ? 'text-success' : 'text-warning'}`}>
          {status.loaded ? 'Loaded' : 'Idle'}
        </span>
      </div>
      {status.loaded && (
        <div className="pt-1">
          <div className="h-1 w-full bg-line rounded-full overflow-hidden">
            <div className="h-full bg-success animate-pulse" style={{ width: '100%' }} />
          </div>
        </div>
      )}
    </div>
  );
}

function SystemStatusPanel({ status }: { status: any }) {
  if (!status) return <div className="text-[10px] text-ink/40 italic">Health data unavailable.</div>;

  return (
    <div className="space-y-2">
      {Object.entries(status.checks || {}).map(([key, ok]) => (
        <div key={key} className="flex justify-between items-center group">
          <span className="text-[10px] text-ink/40 capitalize">{key.replace(/_/g, ' ')}</span>
          <div className="flex items-center gap-1.5">
            <span className={`text-[12px] font-bold ${ok ? 'text-success' : 'text-danger'}`}>
              {ok ? 'PASS' : 'FAIL'}
            </span>
            <div className={`w-1 h-1 rounded-full ${ok ? 'bg-success' : 'bg-danger'}`} />
          </div>
        </div>
      ))}
    </div>
  );
}
