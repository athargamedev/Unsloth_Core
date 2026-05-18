import { useState, useEffect, useRef, useCallback } from 'react';
import { motion } from 'motion/react';
import {
  FileText,
  Database,
  Shield,
  CheckCircle,
  Play,
  ChevronRight,
  Terminal,
  AlertTriangle,
  Loader,
  FlaskConical,
  Users,
  BarChart3,
  ChevronDown,
  ChevronUp,
  ListChecks,
} from 'lucide-react';
import { cn } from '../lib/utils';
import { fetchJson, fetchOptionalJson } from '../api';
import type { AvailableCommand, Subject, QualitySummary, QualityFailure } from '../api';

interface DatasetPipelinePanelProps {
  availableCommands: AvailableCommand[];
  subjects: Subject[];
  onTriggerCommand: (payload: Record<string, unknown>) => void;
  jobs: Array<{ id: string; name: string; status: string; type: string; command?: string[]; logs?: string[] }>;
}

interface PipelineStep {
  id: string;
  label: string;
  icon: React.ReactNode;
  color: string;
  commandId: string;
  buildPayload: (subjectPath: string, npcKey: string, technique: string) => Record<string, unknown>;
  status: 'idle' | 'running' | 'completed' | 'failed';
  log: string[];
}

const TECHNIQUES = ['template', 'docs', 'ollama', 'openai', 'anthropic'] as const;
type Technique = (typeof TECHNIQUES)[number];

export function DatasetPipelinePanel({ availableCommands, subjects, onTriggerCommand, jobs }: DatasetPipelinePanelProps) {
  const [selectedSubjectId, setSelectedSubjectId] = useState<string>('');
  const [selectedTechnique, setSelectedTechnique] = useState<Technique>('template');
  const [qualitySummary, setQualitySummary] = useState<QualitySummary | null>(null);
  const [qualityFailures, setQualityFailures] = useState<QualityFailure[]>([]);
  const [loadingQuality, setLoadingQuality] = useState(false);
  const [qualityError, setQualityError] = useState<string | null>(null);
  const [showFailures, setShowFailures] = useState(false);
  const logsEndRef = useRef<HTMLDivElement>(null);

  const selectedSubject = subjects.find((s) => s.id === selectedSubjectId);
  const hasSelection = !!selectedSubject;

  // Build the npc key from the subject id (it's already the key)
  const npcKey = selectedSubjectId;

  // Pipeline steps state
  const [pipelineSteps, setPipelineSteps] = useState<PipelineStep[]>([
    {
      id: 'validate-spec',
      label: 'Validate Spec',
      icon: <FileText className="w-3.5 h-3.5" />,
      color: 'accent',
      commandId: 'validate-spec',
      buildPayload: (subjectPath: string) => ({
        commandId: 'validate-spec',
        type: 'Validation',
        spec: subjectPath,
        options: { generationReady: true },
      }),
      status: 'idle',
      log: [],
    },
    {
      id: 'dataset-generate',
      label: 'Generate Dataset',
      icon: <Database className="w-3.5 h-3.5" />,
      color: 'accent',
      commandId: 'dataset-generate',
      buildPayload: (subjectPath: string, npcKey: string, technique: string) => ({
        commandId: 'dataset-generate',
        type: 'Dataset',
        spec: subjectPath,
        options: { technique },
      }),
      status: 'idle',
      log: [],
    },
    {
      id: 'dataset-sanitize',
      label: 'Sanitize Dataset',
      icon: <Shield className="w-3.5 h-3.5" />,
      color: 'warning',
      commandId: 'dataset-sanitize',
      buildPayload: (_subjectPath: string, npcKey: string, technique: string) => ({
        commandId: 'dataset-sanitize',
        type: 'Dataset',
        options: { datasetPath: `subjects/datasets/${npcKey}/${technique}/train.jsonl` },
      }),
      status: 'idle',
      log: [],
    },
    {
      id: 'dataset-eval',
      label: 'Evaluate Dataset',
      icon: <FlaskConical className="w-3.5 h-3.5" />,
      color: 'warning',
      commandId: 'dataset-eval',
      buildPayload: (subjectPath: string, npcKey: string, technique: string) => ({
        commandId: 'dataset-eval',
        type: 'Dataset',
        options: { spec: subjectPath, technique },
      }),
      status: 'idle',
      log: [],
    },
  ]);

  // Sync job logs into pipeline steps
  useEffect(() => {
    for (const step of pipelineSteps) {
      if (step.status !== 'running') continue;
      const matchingJob = jobs.find((j) => j.command?.join(' ').includes(step.commandId));
      if (matchingJob) {
        step.log = [...(matchingJob.logs || [])];
        if (matchingJob.status === 'completed') {
          step.status = 'completed';
        } else if (matchingJob.status === 'failed') {
          step.status = 'failed';
        }
      }
    }
    setPipelineSteps([...pipelineSteps]);
  }, [jobs]);

  // Auto-scroll logs
  useEffect(() => {
    if (logsEndRef.current) {
      logsEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [pipelineSteps]);

  // Fetch quality results when dataset-eval step completes
  useEffect(() => {
    const evalStep = pipelineSteps.find((s) => s.id === 'dataset-eval');
    if (!evalStep || evalStep.status !== 'completed' || !npcKey) return;

    const fetchQualityResults = async () => {
      setLoadingQuality(true);
      setQualityError(null);
      try {
        const [summary, failures] = await Promise.all([
          fetchOptionalJson<QualitySummary>(`/api/datasets/quality-summary/${npcKey}/${selectedTechnique}`),
          fetchOptionalJson<QualityFailure[]>(`/api/datasets/quality-failures/${npcKey}/${selectedTechnique}`),
        ]);
        if (summary) setQualitySummary(summary);
        if (failures) setQualityFailures(failures);
      } catch (err) {
        setQualityError(err instanceof Error ? err.message : 'Failed to load quality results');
      } finally {
        setLoadingQuality(false);
      }
    };

    fetchQualityResults();
  }, [pipelineSteps, npcKey, selectedTechnique]);

  // Reset quality results when NPC or technique changes
  useEffect(() => {
    setQualitySummary(null);
    setQualityFailures([]);
    setQualityError(null);
    setShowFailures(false);
  }, [selectedSubjectId, selectedTechnique]);

  const runPipelineStep = useCallback(
    (step: PipelineStep) => {
      if (!selectedSubject) return;
      const payload = step.buildPayload(selectedSubject.path, npcKey, selectedTechnique);
      step.status = 'running';
      step.log = [];
      setPipelineSteps([...pipelineSteps]);
      onTriggerCommand(payload);
    },
    [selectedSubject, npcKey, selectedTechnique, pipelineSteps, onTriggerCommand],
  );

  const runAllSteps = async () => {
    for (const step of pipelineSteps) {
      if (step.status === 'completed') continue;
      runPipelineStep(step);
      // Yield to let the job register before polling
      await new Promise((resolve) => setTimeout(resolve, 1000));
    }
  };

  const getStepStatusIcon = (status: string) => {
    switch (status) {
      case 'completed':
        return <CheckCircle className="w-4 h-4 text-success" />;
      case 'running':
        return <Loader className="w-4 h-4 text-accent animate-spin" />;
      case 'failed':
        return <AlertTriangle className="w-4 h-4 text-danger" />;
      default:
        return <ChevronRight className="w-4 h-4 text-ink/30" />;
    }
  };

  const getPassBarColor = (rate: number) => {
    if (rate >= 0.8) return 'bg-success';
    if (rate >= 0.5) return 'bg-warning';
    return 'bg-danger';
  };

  const getPassTextColor = (rate: number) => {
    if (rate >= 0.8) return 'text-success';
    if (rate >= 0.5) return 'text-warning';
    return 'text-danger';
  };

  const allStepsCompleted = pipelineSteps.every((s) => s.status === 'completed');
  const anyStepRunning = pipelineSteps.some((s) => s.status === 'running');

  // Derive if all prior steps before eval are completed
  const evalStep = pipelineSteps.find((s) => s.id === 'dataset-eval');
  const priorStepsCompleted = pipelineSteps
    .filter((s) => s.id !== 'dataset-eval')
    .every((s) => s.status === 'completed');

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      <div className="flex-1 overflow-auto custom-scrollbar p-4 space-y-6">
        {/* Header */}
        <div>
          <div className="flex items-center gap-2 mb-1">
            <ListChecks className="w-4 h-4 text-accent" />
            <h3 className="text-xs font-bold text-ink-bright uppercase tracking-widest">Dataset Pipeline</h3>
          </div>
          <p className="text-[10px] text-ink/40">
            Validate, generate, sanitize, and evaluate NPC training datasets through a four-stage pipeline.
          </p>
        </div>

        {/* Selection Panel */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {/* NPC Selector */}
          <div className="p-3 border border-line bg-surface/50 rounded-sm">
            <label className="block text-[10px] font-bold text-ink/40 uppercase tracking-wider mb-2">
              <Users className="w-3 h-3 inline mr-1" />
              Select NPC
            </label>
            {subjects.length === 0 ? (
              <p className="text-[12px] text-ink/30 italic">No NPC subjects available.</p>
            ) : (
              <select
                value={selectedSubjectId}
                onChange={(e) => setSelectedSubjectId(e.target.value)}
                className="w-full p-2 bg-bg border border-line rounded text-[11px] focus:outline-none focus:border-accent font-mono"
              >
                <option value="" disabled>
                  -- Choose an NPC --
                </option>
                {subjects.map((subject) => (
                  <option key={subject.id} value={subject.id}>
                    {subject.id} ({subject.path})
                  </option>
                ))}
              </select>
            )}
            {selectedSubject && (
              <div className="mt-2 text-[10px] text-ink/40 space-y-1">
                <p>
                  Spec: <code className="text-accent">{selectedSubject.path}</code>
                </p>
              </div>
            )}
          </div>

          {/* Technique Selector */}
          <div className="p-3 border border-line bg-surface/50 rounded-sm">
            <label className="block text-[10px] font-bold text-ink/40 uppercase tracking-wider mb-2">
              <Database className="w-3 h-3 inline mr-1" />
              Generation Technique
            </label>
            <select
              value={selectedTechnique}
              onChange={(e) => setSelectedTechnique(e.target.value as Technique)}
              className="w-full p-2 bg-bg border border-line rounded text-[11px] focus:outline-none focus:border-accent font-mono"
            >
              {TECHNIQUES.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
            <p className="mt-2 text-[10px] text-ink/40">
              Technique controls how the dataset is generated. <code className="text-accent">template</code> uses deterministic templates;{' '}
              <code className="text-accent">docs</code> uses curated documentation.
            </p>
          </div>
        </div>

        {/* Pipeline Steps */}
        <div className="border border-line bg-surface/30 rounded-sm">
          <div className="p-3 border-b border-line bg-surface/50">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Play className="w-3.5 h-3.5 text-accent" />
                <span className="text-[10px] font-bold text-ink-bright uppercase tracking-wider">
                  Pipeline Steps
                </span>
              </div>
              <button
                onClick={runAllSteps}
                disabled={!hasSelection || allStepsCompleted || anyStepRunning}
                className="px-3 py-1 bg-accent text-bg text-[10px] font-bold rounded-sm hover:brightness-110 disabled:opacity-40 transition-all flex items-center gap-1.5"
              >
                <Play className="w-3 h-3" />
                Run All Steps
              </button>
            </div>
          </div>
          <div className="p-3 space-y-2">
            {pipelineSteps.map((step) => (
              <div
                key={step.id}
                className={cn(
                  'p-3 border rounded-sm transition-colors',
                  step.status === 'completed'
                    ? 'border-success/30 bg-success/5'
                    : step.status === 'running'
                      ? 'border-accent/30 bg-accent/5'
                      : step.status === 'failed'
                        ? 'border-danger/30 bg-danger/5'
                        : 'border-line/40 bg-surface/30',
                )}
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <div className="w-6 h-6 rounded-full bg-surface border border-line flex items-center justify-center">
                      {getStepStatusIcon(step.status)}
                    </div>
                    <div>
                      <span className="text-[12px] font-bold text-ink-bright">{step.label}</span>
                      <span className="text-[9px] text-ink/30 ml-2 font-mono">{step.commandId}</span>
                    </div>
                  </div>
                  <button
                    onClick={() => runPipelineStep(step)}
                    disabled={!hasSelection || step.status === 'running' || step.status === 'completed'}
                    className={cn(
                      'px-2.5 py-1 text-[10px] font-bold rounded-sm transition-all flex items-center gap-1',
                      step.status === 'completed'
                        ? 'bg-success/10 text-success border border-success/30'
                        : step.status === 'running'
                          ? 'bg-accent/10 text-accent border border-accent/30'
                          : 'bg-surface border border-line text-ink/60 hover:bg-line/20',
                    )}
                  >
                    {step.status === 'completed'
                      ? 'Completed'
                      : step.status === 'running'
                        ? 'Running...'
                        : step.status === 'failed'
                          ? 'Retry'
                          : 'Run'}
                  </button>
                </div>
                {/* Step logs */}
                {step.log.length > 0 && (
                  <div className="mt-3 p-2 bg-black/40 border border-line/30 rounded max-h-20 overflow-y-auto font-mono text-[9px] leading-relaxed custom-scrollbar">
                    {step.log.slice(-10).map((line, li) => (
                      <div
                        key={li}
                        className={cn(
                          'whitespace-pre-wrap',
                          line.includes('[ERROR]') || line.includes('failed')
                            ? 'text-danger'
                            : line.includes('[STDERR]')
                              ? 'text-warning'
                              : 'text-ink/50',
                        )}
                      >
                        {line}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>

        {/* Quality Results Section */}
        <div className="border border-line bg-surface/30 rounded-sm">
          <div className="p-3 border-b border-line bg-surface/50">
            <div className="flex items-center gap-2">
              <BarChart3 className="w-3.5 h-3.5 text-accent" />
              <span className="text-[10px] font-bold text-ink-bright uppercase tracking-wider">
                Dataset Quality Results
              </span>
            </div>
          </div>

          <div className="p-3">
            {!evalStep || evalStep.status !== 'completed' ? (
              <div className="flex items-center justify-center py-6 text-[11px] text-ink/30 italic">
                Run the Evaluate Dataset step above to see quality results here.
              </div>
            ) : loadingQuality ? (
              <div className="flex items-center justify-center py-6">
                <Loader className="w-4 h-4 text-accent animate-spin mr-2" />
                <span className="text-[11px] text-ink/50">Loading quality results...</span>
              </div>
            ) : qualityError ? (
              <div className="p-3 border border-warning/30 bg-warning/5 rounded-sm">
                <div className="flex items-center gap-2 text-warning font-bold text-[11px]">
                  <AlertTriangle className="w-3.5 h-3.5" />
                  Quality Results Unavailable
                </div>
                <p className="text-[11px] text-ink/50 mt-1">{qualityError}</p>
              </div>
            ) : qualitySummary ? (
              <div className="space-y-4">
                {/* Summary Card */}
                <motion.div
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.3 }}
                  className="p-4 border border-line/50 bg-surface/40 rounded-sm"
                >
                  <div className="flex items-center justify-between mb-3">
                    <span className="text-[10px] font-bold text-ink/50 uppercase tracking-wider">Overall Quality</span>
                    <span className="text-[9px] font-mono text-ink/30">
                      Judge: {qualitySummary.judge_model} &middot; {qualitySummary.created_at}
                    </span>
                  </div>

                  <div className="grid grid-cols-4 gap-3 mb-3">
                    <div className="text-center">
                      <div className="text-lg font-bold text-ink-bright font-mono">{qualitySummary.total}</div>
                      <div className="text-[9px] text-ink/40 uppercase tracking-wider">Total</div>
                    </div>
                    <div className="text-center">
                      <div className="text-lg font-bold text-success font-mono">{qualitySummary.passed}</div>
                      <div className="text-[9px] text-ink/40 uppercase tracking-wider">Passed</div>
                    </div>
                    <div className="text-center">
                      <div className="text-lg font-bold text-danger font-mono">{qualitySummary.failed}</div>
                      <div className="text-[9px] text-ink/40 uppercase tracking-wider">Failed</div>
                    </div>
                    <div className="text-center">
                      <div className={cn('text-lg font-bold font-mono', getPassTextColor(qualitySummary.pass_rate))}>
                        {(qualitySummary.pass_rate * 100).toFixed(0)}%
                      </div>
                      <div className="text-[9px] text-ink/40 uppercase tracking-wider">Pass Rate</div>
                    </div>
                  </div>

                  {/* Pass rate bar */}
                  <div className="w-full h-2 bg-bg rounded-sm overflow-hidden">
                    <motion.div
                      initial={{ width: 0 }}
                      animate={{ width: `${qualitySummary.pass_rate * 100}%` }}
                      transition={{ duration: 0.6, ease: 'easeOut' }}
                      className={cn('h-full rounded-sm', getPassBarColor(qualitySummary.pass_rate))}
                    />
                  </div>
                </motion.div>

                {/* Category Breakdown */}
                {Object.keys(qualitySummary.categories).length > 0 && (
                  <motion.div
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.3, delay: 0.1 }}
                    className="p-3 border border-line/50 bg-surface/40 rounded-sm"
                  >
                    <div className="text-[10px] font-bold text-ink/50 uppercase tracking-wider mb-2">
                      Category Breakdown
                    </div>
                    <div className="overflow-x-auto">
                      <table className="w-full text-[11px] font-mono">
                        <thead>
                          <tr className="border-b border-line/30">
                            <th className="text-left py-1.5 pr-3 text-ink/40 font-bold">Category</th>
                            <th className="text-right px-2 py-1.5 text-ink/40 font-bold">Total</th>
                            <th className="text-right px-2 py-1.5 text-ink/40 font-bold">Passed</th>
                            <th className="text-right pl-2 py-1.5 text-ink/40 font-bold">Pass Rate</th>
                          </tr>
                        </thead>
                        <tbody>
                          {Object.entries(qualitySummary.categories).map(([category, data]) => (
                            <tr key={category} className="border-b border-line/10">
                              <td className="py-1.5 pr-3 text-ink-bright capitalize">{category.replace(/_/g, ' ')}</td>
                              <td className="text-right px-2 py-1.5 text-ink/60">{data.total}</td>
                              <td className="text-right px-2 py-1.5 text-ink/60">{data.passed}</td>
                              <td className={cn('text-right pl-2 py-1.5 font-bold', getPassTextColor(data.pass_rate))}>
                                {(data.pass_rate * 100).toFixed(0)}%
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </motion.div>
                )}

                {/* Metric Breakdown */}
                {Object.keys(qualitySummary.metrics).length > 0 && (
                  <motion.div
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.3, delay: 0.2 }}
                    className="p-3 border border-line/50 bg-surface/40 rounded-sm"
                  >
                    <div className="text-[10px] font-bold text-ink/50 uppercase tracking-wider mb-2">
                      Metric Breakdown
                    </div>
                    <div className="overflow-x-auto">
                      <table className="w-full text-[11px] font-mono">
                        <thead>
                          <tr className="border-b border-line/30">
                            <th className="text-left py-1.5 pr-3 text-ink/40 font-bold">Metric</th>
                            <th className="text-right px-2 py-1.5 text-ink/40 font-bold">Count</th>
                            <th className="text-right px-2 py-1.5 text-ink/40 font-bold">Avg Score</th>
                            <th className="text-right pl-2 py-1.5 text-ink/40 font-bold">Pass Rate</th>
                          </tr>
                        </thead>
                        <tbody>
                          {Object.entries(qualitySummary.metrics).map(([metric, data]) => (
                            <tr key={metric} className="border-b border-line/10">
                              <td className="py-1.5 pr-3 text-ink-bright">{metric}</td>
                              <td className="text-right px-2 py-1.5 text-ink/60">{data.count}</td>
                              <td className="text-right px-2 py-1.5 text-ink/60">{data.average_score.toFixed(3)}</td>
                              <td className={cn('text-right pl-2 py-1.5 font-bold', getPassTextColor(data.pass_rate))}>
                                {(data.pass_rate * 100).toFixed(0)}%
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </motion.div>
                )}

                {/* Failures Section */}
                {qualityFailures.length > 0 && (
                  <motion.div
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.3, delay: 0.3 }}
                    className="p-3 border border-danger/30 bg-danger/5 rounded-sm"
                  >
                    <button
                      onClick={() => setShowFailures(!showFailures)}
                      className="w-full flex items-center justify-between"
                    >
                      <div className="flex items-center gap-2">
                        <AlertTriangle className="w-3.5 h-3.5 text-danger" />
                        <span className="text-[10px] font-bold text-danger uppercase tracking-wider">
                          {qualityFailures.length} Failure{qualityFailures.length !== 1 ? 's' : ''}
                        </span>
                      </div>
                      {showFailures ? (
                        <ChevronUp className="w-3.5 h-3.5 text-danger/60" />
                      ) : (
                        <ChevronDown className="w-3.5 h-3.5 text-danger/60" />
                      )}
                    </button>

                    {showFailures && (
                      <div className="mt-3 space-y-2">
                        {qualityFailures.map((failure, idx) => (
                          <motion.div
                            key={`${failure.test_name}-${idx}`}
                            initial={{ opacity: 0, height: 0 }}
                            animate={{ opacity: 1, height: 'auto' }}
                            transition={{ duration: 0.2, delay: idx * 0.03 }}
                            className="p-2.5 border border-danger/20 bg-danger/5 rounded-sm"
                          >
                            <div className="flex items-start justify-between gap-2 mb-1">
                              <span className="text-[11px] font-bold text-ink-bright">{failure.test_name}</span>
                              <span className="text-[9px] font-mono text-ink/30 shrink-0">
                                Score: {failure.metric.score.toFixed(3)} / Threshold: {failure.metric.threshold}
                              </span>
                            </div>
                            <p className="text-[10px] text-ink/50 mb-1">{failure.metric.reason}</p>
                            {failure.metric.error && (
                              <p className="text-[10px] text-danger font-mono mt-1">Error: {failure.metric.error}</p>
                            )}
                            {failure.input && (
                              <div className="mt-1.5 p-1.5 bg-black/30 border border-line/20 rounded text-[9px] font-mono text-ink/40 max-h-12 overflow-y-auto">
                                <div className="text-[8px] text-ink/30 uppercase tracking-wider mb-0.5">Input:</div>
                                {failure.input.length > 200 ? `${failure.input.slice(0, 200)}...` : failure.input}
                              </div>
                            )}
                          </motion.div>
                        ))}
                      </div>
                    )}
                  </motion.div>
                )}

                {/* No failures message */}
                {qualityFailures.length === 0 && (
                  <motion.div
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    transition={{ duration: 0.3, delay: 0.3 }}
                    className="flex items-center gap-2 p-3 border border-success/20 bg-success/5 rounded-sm"
                  >
                    <CheckCircle className="w-3.5 h-3.5 text-success shrink-0" />
                    <span className="text-[11px] text-success font-bold">All tests passed — no quality failures.</span>
                  </motion.div>
                )}
              </div>
            ) : null}
          </div>
        </div>

        {/* Info */}
        <div className="p-3 border border-line/30 bg-surface/20 rounded-sm">
          <div className="flex items-start gap-2 text-[10px] text-ink/40">
            <Terminal className="w-3 h-3 mt-0.5 shrink-0 text-accent" />
            <p>
              The dataset pipeline validates NPC spec readiness, generates training data using the selected technique,
              sanitizes artifacts, and evaluates quality using a local judge model. Quality results appear automatically
              after evaluation completes.
            </p>
          </div>
        </div>

        {/* Scroll anchor for auto-scroll */}
        <div ref={logsEndRef} />
      </div>
    </div>
  );
}
