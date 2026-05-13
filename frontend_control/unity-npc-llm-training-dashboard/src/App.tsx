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
import { fetchJson } from './api';
import type { AvailableCommand, TrainingConfig } from './api';
import { useJobs } from './hooks/useJobs';
import { useSystemStatus } from './hooks/useSystemStatus';
import { useTelemetry } from './hooks/useTelemetry';
import { useDatasets } from './hooks/useDatasets';
import { AIAssistant } from './components/AIAssistant';
import { OperationsMatrix } from './components/OperationsMatrix';
import { DatasetFactory } from './components/DatasetFactory';
import { TrainingSuite } from './components/TrainingSuite';
import { TensorBoardPanel } from './components/TensorBoardPanel';
import { SystemHub } from './components/SystemHub';
import { ModelComparison } from './components/ModelComparison';
import { Card } from './components/Card';

export default function App() {
  const [activeTab, setActiveTab] = useState<'overview' | 'training' | 'datasets' | 'compare' | 'analytics' | 'commands'>('overview');
  const [logs, setLogs] = useState<string[]>([]);
  const [analyticsData, setAnalyticsData] = useState<Array<{ step: number; loss: number; acc: number; lr: number }>>([]);
  const [uiError, setUiError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [commandModalOpen, setCommandModalOpen] = useState(false);
  const [selectedCommand, setSelectedCommand] = useState<string | null>(null);
  const [commandPayload, setCommandPayload] = useState<any>({});

  const [trainingConfig, setTrainingConfig] = useState<TrainingConfig>({
    spec: 'subjects/chemistry_instructor.json',
    preset: 'fast-3b',
    learningRate: '2e-4',
    batchSize: 4,
    epochs: 3,
    rank: 16,
    alpha: 32,
    baseModel: 'mistralai/Mistral-7B-Instruct-v0.2',
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
    stopJob,
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

  // --- Data Fetching ---

  const fetchData = async () => {
    setIsLoading(true);
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
      ]);
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

  // --- Handlers ---

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

  const handleToggleExecutionMode = async () => {
    try {
      await toggleExecutionMode();
      setUiError(null);
    } catch (error) {
      setUiError(error instanceof Error ? error.message : 'Failed to toggle execution mode');
    }
  };

  const triggerCommand = async (payload: Record<string, unknown>) => {
    const response = await fetch('/api/commands/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!response.ok) {
      const err = await response.json().catch(() => ({}));
      throw new Error(err.error || 'Failed to start command');
    }
    await fetchData();
  };

  const getDefaultPayloadForCommand = (commandId: string): Record<string, unknown> => {
    if (commandSchemas[commandId]) {
      return { ...commandSchemas[commandId] };
    }
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

  const handleStopJob = async (id: string) => {
    try {
      await stopJob(id);
      await fetchData();
    } catch (error) {
      setUiError(error instanceof Error ? error.message : 'Failed to stop job');
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
  };

  const handleGenerateDataset = async () => {
    try {
      await triggerCommand({ commandId: 'dataset-generate', type: 'Dataset', spec: trainingConfig.spec });
    } catch (error) {
      setUiError(error instanceof Error ? error.message : 'Dataset generation failed');
    }
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
      await triggerCommand({ commandId: 'dataset-generate', type: 'Dataset', spec: trainingConfig.spec });
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

  const handleSetCommandPayload = (field: string, value: string) => {
    setCommandPayload((prev: Record<string, unknown>) => ({ ...prev, [field]: value }));
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
                activeTab === 'overview' ? "border-accent text-ink-bright" : "border-transparent text-ink/40 hover:text-ink/60",
              )}
            >
              Operations Matrix
            </button>
            <button
              onClick={() => setActiveTab('datasets')}
              className={cn(
                "px-4 py-2 text-[10px] font-bold uppercase tracking-widest border-b-2 transition-colors",
                activeTab === 'datasets' ? "border-accent text-ink-bright" : "border-transparent text-ink/40 hover:text-ink/60",
              )}
            >
              Dataset Factory
            </button>
            <button
              onClick={() => setActiveTab('training')}
              className={cn(
                "px-4 py-2 text-[10px] font-bold uppercase tracking-widest border-b-2 transition-colors",
                activeTab === 'training' ? "border-accent text-ink-bright" : "border-transparent text-ink/40 hover:text-ink/60",
              )}
            >
              Training Suite
            </button>
            <button
              onClick={() => setActiveTab('analytics')}
              className={cn(
                "px-4 py-2 text-[10px] font-bold uppercase tracking-widest border-b-2 transition-colors",
                activeTab === 'analytics' ? "border-accent text-ink-bright" : "border-transparent text-ink/40 hover:text-ink/60",
              )}
            >
              TensorBoard
            </button>
            <button
              onClick={() => setActiveTab('commands')}
              className={cn(
                "px-4 py-2 text-[10px] font-bold uppercase tracking-widest border-b-2 transition-colors",
                activeTab === 'commands' ? "border-accent text-ink-bright" : "border-transparent text-ink/40 hover:text-ink/60",
              )}
            >
              System Hub
            </button>
            <button
              onClick={() => setActiveTab('compare')}
              className={cn(
                "px-4 py-2 text-[10px] font-bold uppercase tracking-widest border-b-2 transition-colors relative",
                activeTab === 'compare' ? "border-accent text-ink-bright" : "border-transparent text-ink/40 hover:text-ink/60",
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
              <OperationsMatrix
                jobs={jobs}
                filteredJobs={filteredJobs}
                selectedJobIds={selectedJobIds}
                selectedJobId={selectedJobId}
                activeFilter={activeFilter}
                onSelectJob={handleSelectJob}
                onToggleJobSelection={toggleJobSelection}
                onSetActiveFilter={handleSetActiveFilter}
                onStopJob={handleStopJob}
                onExportCsv={exportJobsCsv}
                onOpenComparison={handleOpenComparison}
                onManageJob={handleManageJob}
              />
            )}

            {activeTab === 'training' && (
              <TrainingSuite
                subjects={subjects}
                trainingConfig={trainingConfig}
                onUpdateTrainingConfig={handleUpdateTrainingConfig}
                onLaunchTraining={handleLaunchTraining}
              />
            )}

            {activeTab === 'analytics' && (
              <TensorBoardPanel
                analyticsData={analyticsData}
                onRefresh={fetchData}
              />
            )}

            {activeTab === 'commands' && (
              <SystemHub
                availableCommands={availableCommands}
                onTriggerCommand={handleSystemHubCommand}
              />
            )}

            {activeTab === 'compare' && (
              <ModelComparison
                selectedJobIds={selectedJobIds}
                jobs={jobs}
                onToggleJobSelection={toggleJobSelection}
                onClearSelection={handleClearSelection}
                onNavigateTo={setActiveTab}
              />
            )}

            {activeTab === 'datasets' && (
              <DatasetFactory
                datasets={datasets}
                runs={runs}
                exportArtifacts={exportArtifacts}
                trainingConfig={trainingConfig}
                onGenerateDataset={handleGenerateDataset}
              />
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
                  className="w-full py-2 bg-accent hover:bg-accent/80 text-bg rounded-sm text-[11px] font-bold uppercase transition-all active:scale-95 shadow-lg shadow-accent/20"
                >
                  Run Dataset Generator
                </button>
                <button
                  onClick={handleRightSidebarLaunchTraining}
                  className="w-full py-2 bg-panel border border-line hover:border-accent text-ink rounded-sm text-[11px] font-bold uppercase transition-colors"
                >
                  Initialize LoRA Train
                </button>
                <button
                  onClick={handleRightSidebarExport}
                  className="w-full py-2 bg-panel border border-line hover:border-accent text-ink rounded-sm text-[11px] font-bold uppercase transition-colors"
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
                      <div className="text-[11px] font-bold">{status?.executionMode?.toUpperCase() || 'LOCAL'}</div>
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
            <div className="w-1.5 h-1.5 rounded-full bg-success" />
            <span className="text-success font-bold">System Healthy</span>
          </div>
          <span>Session: {status?.executionMode?.toUpperCase() || 'LOCAL'}</span>
          <span className="text-ink/20">©2026 NPC_GEN_CORE</span>
        </div>
      </footer>

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

                {Object.keys(commandPayload).filter((key: string) => key !== 'commandId' && key !== 'type').map((field: string) => (
                  <div key={field}>
                    <label className="block text-sm font-bold text-ink/60 mb-2 capitalize">{field.replace(/([A-Z])/g, ' $1')}</label>
                    <input
                      type="text"
                      value={String(commandPayload[field] || '')}
                      onChange={(e) => handleSetCommandPayload(field, e.target.value)}
                      className="w-full p-2 bg-bg border border-line rounded text-sm focus:outline-none focus:border-accent"
                    />
                  </div>
                ))}

                <div className="flex gap-2 pt-4">
                  <button
                    onClick={async () => {
                      try {
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
