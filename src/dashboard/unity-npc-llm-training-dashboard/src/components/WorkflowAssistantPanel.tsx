import { useState, useEffect, useRef } from 'react';
import { motion } from 'motion/react';
import { FileText, Database, Shield, CheckCircle, Play, ChevronRight, BookOpen, ExternalLink, Terminal, AlertTriangle, Loader } from 'lucide-react';
import { cn } from '../lib/utils';
import { fetchJson } from '../api';
import type { ManifestInfo, ManifestDetail, ManifestSource, AvailableCommand } from '../api';

interface WorkflowAssistantPanelProps {
  availableCommands: AvailableCommand[];
  onTriggerCommand: (payload: Record<string, unknown>) => void;
  jobs: Array<{ id: string; name: string; status: string; type: string; command?: string[]; logs?: string[] }>;
}

interface PipelineStep {
  id: string;
  label: string;
  icon: React.ReactNode;
  color: string;
  commandId: string;
  buildPayload: (spec: string, manifest: string) => Record<string, unknown>;
  status: 'idle' | 'running' | 'completed' | 'failed';
  log: string[];
}

export function WorkflowAssistantPanel({ availableCommands, onTriggerCommand, jobs }: WorkflowAssistantPanelProps) {
  const [manifests, setManifests] = useState<ManifestInfo[]>([]);
  const [selectedManifest, setSelectedManifest] = useState<string>('');
  const [manifestDetail, setManifestDetail] = useState<ManifestDetail | null>(null);
  const [selectedSources, setSelectedSources] = useState<Set<number>>(new Set());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const logsEndRef = useRef<HTMLDivElement>(null);

  // Pipeline steps state
  const [pipelineSteps, setPipelineSteps] = useState<PipelineStep[]>([
    {
      id: 'generate',
      label: 'Generate Dataset',
      icon: <Database className="w-3.5 h-3.5" />,
      color: 'accent',
      commandId: 'docs-manifest-generate',
      buildPayload: (spec, manifest) => ({
        commandId: 'docs-manifest-generate',
        type: 'Dataset',
        spec: spec,
        manifest: manifest,
        options: { technique: 'docs' },
      }),
      status: 'idle',
      log: [],
    },
    {
      id: 'sanitize',
      label: 'Sanitize Dataset',
      icon: <Shield className="w-3.5 h-3.5" />,
      color: 'warning',
      commandId: 'dataset-sanitize',
      buildPayload: (spec, manifest) => ({
        commandId: 'dataset-sanitize',
        type: 'Dataset',
        options: { datasetPath: `subjects/datasets/workflow_assistant/docs/train.jsonl` },
      }),
      status: 'idle',
      log: [],
    },
    {
      id: 'validate',
      label: 'Validate Config',
      icon: <CheckCircle className="w-3.5 h-3.5" />,
      color: 'accent',
      commandId: 'validate-config',
      buildPayload: (spec, manifest) => ({
        commandId: 'validate-config',
        type: 'Validation',
        spec: spec,
      }),
      status: 'idle',
      log: [],
    },
  ]);

  // Load manifests on mount
  useEffect(() => {
    const loadManifests = async () => {
      setLoading(true);
      try {
        const data = await fetchJson<ManifestInfo[]>('/api/manifests');
        setManifests(data);
        if (data.length > 0) {
          setSelectedManifest(data[0].name);
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load manifests');
      } finally {
        setLoading(false);
      }
    };
    loadManifests();
  }, []);

  // Load manifest detail when selection changes
  useEffect(() => {
    if (!selectedManifest) return;
    const loadDetail = async () => {
      try {
        const detail = await fetchJson<ManifestDetail>(`/api/manifests/${selectedManifest}`);
        setManifestDetail(detail);
        // Auto-select all sources
        setSelectedSources(new Set(detail.sources.map((_, i) => i)));
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load manifest detail');
      }
    };
    loadDetail();
  }, [selectedManifest]);

  // Sync job logs into pipeline steps
  useEffect(() => {
    for (const step of pipelineSteps) {
      if (step.status !== 'running') continue;
      const matchingJob = jobs.find(j => j.command?.join(' ').includes(step.commandId));
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

  useEffect(() => {
    if (logsEndRef.current) {
      logsEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [pipelineSteps]);

  const toggleSource = (index: number) => {
    const next = new Set(selectedSources);
    if (next.has(index)) next.delete(index);
    else next.add(index);
    setSelectedSources(next);
  };

  const runPipelineStep = (step: PipelineStep) => {
    const spec = 'subjects/workflow_assistant.json';
    const manifestPath = `docs/corpora/${selectedManifest}`;
    const payload = step.buildPayload(spec, manifestPath);
    step.status = 'running';
    step.log = [];
    setPipelineSteps([...pipelineSteps]);
    onTriggerCommand(payload);
  };

  const runAllSteps = async () => {
    for (const step of pipelineSteps) {
      if (step.status === 'completed') continue;
      runPipelineStep(step);
      // Wait a moment for the job to register, then poll for completion
      await new Promise(resolve => setTimeout(resolve, 1000));
      // The job sync effect will update status
    }
  };

  const getStepStatusIcon = (status: string) => {
    switch (status) {
      case 'completed': return <CheckCircle className="w-4 h-4 text-success" />;
      case 'running': return <Loader className="w-4 h-4 text-accent animate-spin" />;
      case 'failed': return <AlertTriangle className="w-4 h-4 text-danger" />;
      default: return <ChevronRight className="w-4 h-4 text-ink/30" />;
    }
  };

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="flex flex-col items-center gap-2">
          <div className="w-6 h-6 border-2 border-accent border-t-transparent rounded-full animate-spin" />
          <span className="text-[12px] text-ink/40">Loading corpus manifests...</span>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex-1 p-6">
        <div className="p-4 border border-danger/30 bg-danger/5 rounded-sm">
          <div className="flex items-center gap-2 text-danger font-bold text-[12px] uppercase tracking-wider">
            <AlertTriangle className="w-4 h-4" /> Error Loading Manifests
          </div>
          <p className="text-[12px] text-ink/60 mt-1">{error}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      <div className="flex-1 overflow-auto custom-scrollbar p-4 space-y-6">
        {/* Header */}
        <div>
          <div className="flex items-center gap-2 mb-1">
            <BookOpen className="w-4 h-4 text-accent" />
            <h3 className="text-xs font-bold text-ink-bright uppercase tracking-widest">Workflow Docs Dataset Generator</h3>
          </div>
          <p className="text-[10px] text-ink/40">
            Generate NPC datasets from curated checked-in documentation and structured reports using the <code className="text-accent">docs</code> technique.
          </p>
        </div>

        {/* Manifest Selection */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <div className="lg:col-span-1 space-y-3">
            <div className="p-3 border border-line bg-surface/50 rounded-sm">
              <label className="block text-[10px] font-bold text-ink/40 uppercase tracking-wider mb-2">Select Corpus Manifest</label>
              {manifests.length === 0 ? (
                <p className="text-[12px] text-ink/30 italic">No manifests found in <code className="text-accent">docs/corpora/</code></p>
              ) : (
                <select
                  value={selectedManifest}
                  onChange={(e) => setSelectedManifest(e.target.value)}
                  className="w-full p-2 bg-bg border border-line rounded text-[11px] focus:outline-none focus:border-accent font-mono"
                >
                  {manifests.map((m) => (
                    <option key={m.name} value={m.name}>
                      {m.manifest_name} ({m.source_count} sources, {m.total_questions} Q)
                    </option>
                  ))}
                </select>
              )}

              {selectedManifest && manifests.find(m => m.name === selectedManifest) && (
                <div className="mt-2 text-[10px] text-ink/40 space-y-1">
                  {(() => {
                    const m = manifests.find(m => m.name === selectedManifest);
                    return m ? (
                      <>
                        <p>{m.description}</p>
                        {m.version && <p className="font-mono">v{m.version}</p>}
                      </>
                    ) : null;
                  })()}
                </div>
              )}
            </div>

            {/* Quick Stats */}
            {manifestDetail && (
              <div className="p-3 border border-line bg-surface/50 rounded-sm">
                <div className="text-[10px] font-bold text-ink/40 uppercase tracking-wider mb-2">Manifest Stats</div>
                <div className="space-y-1.5 text-[11px]">
                  <div className="flex justify-between">
                    <span className="text-ink/50">Sources</span>
                    <span className="font-mono text-ink-bright">{manifestDetail.sources.length}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-ink/50">Selected</span>
                    <span className="font-mono text-accent">{selectedSources.size}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-ink/50">Total Questions</span>
                    <span className="font-mono text-ink-bright">
                      {manifestDetail.sources.reduce((sum, s) => sum + (s.questions?.length || 0), 0)}
                    </span>
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Source Documents */}
          <div className="lg:col-span-2 space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-[10px] font-bold text-ink/40 uppercase tracking-wider">Source Documents</span>
              <button
                onClick={() => {
                  if (manifestDetail) {
                    const all = new Set(manifestDetail.sources.map((_, i) => i));
                    setSelectedSources(selectedSources.size === manifestDetail.sources.length ? new Set() : all);
                  }
                }}
                className="text-[10px] font-bold text-accent hover:brightness-125 uppercase tracking-tighter"
              >
                {manifestDetail && selectedSources.size === manifestDetail.sources.length ? 'Deselect All' : 'Select All'}
              </button>
            </div>

            {!manifestDetail ? (
              <div className="p-6 text-center text-[12px] text-ink/30 italic">Select a manifest above to view source documents.</div>
            ) : (
              <div className="space-y-2">
                {manifestDetail.sources.map((source, idx) => (
                  <motion.div
                    key={source.path}
                    initial={{ opacity: 0, y: -5 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: idx * 0.03 }}
                    className={cn(
                      "p-3 border rounded-sm cursor-pointer transition-all",
                      selectedSources.has(idx)
                        ? "border-accent/40 bg-accent/5"
                        : "border-line/50 bg-surface/30 hover:border-line"
                    )}
                    onClick={() => toggleSource(idx)}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex items-start gap-2 min-w-0">
                        <input
                          type="checkbox"
                          checked={selectedSources.has(idx)}
                          onChange={() => toggleSource(idx)}
                          className="mt-0.5 accent-accent"
                        />
                        <div className="min-w-0">
                          <div className="flex items-center gap-2">
                            <FileText className="w-3 h-3 text-accent shrink-0" />
                            <span className="text-[12px] font-bold text-ink-bright truncate">{source.path}</span>
                            {source.exists === false && (
                              <span className="text-[9px] text-danger uppercase font-bold">Missing</span>
                            )}
                          </div>
                          {source.kind && (
                            <span className="text-[9px] text-ink/30 uppercase tracking-wider">{source.kind}</span>
                          )}
                        </div>
                      </div>
                      <div className="flex items-center gap-2 shrink-0">
                        {source.doc_size && (
                          <span className="text-[9px] font-mono text-ink/30">{source.doc_size}</span>
                        )}
                        <span className="text-[9px] font-mono text-ink/40">{source.questions?.length || 0} questions</span>
                      </div>
                    </div>
                    {/* Section hints */}
                    {source.section_hints && source.section_hints.length > 0 && (
                      <div className="mt-2 flex flex-wrap gap-1">
                        {source.section_hints.map((hint) => (
                          <span key={hint} className="px-1.5 py-0.5 bg-accent/10 border border-accent/20 text-[9px] font-mono text-accent rounded-sm">
                            {hint}
                          </span>
                        ))}
                      </div>
                    )}
                  </motion.div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Pipeline Steps */}
        <div className="border border-line bg-surface/30 rounded-sm">
          <div className="p-3 border-b border-line bg-surface/50">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Play className="w-3.5 h-3.5 text-accent" />
                <span className="text-[10px] font-bold text-ink-bright uppercase tracking-wider">Generation Pipeline</span>
              </div>
              <button
                onClick={runAllSteps}
                disabled={pipelineSteps.every(s => s.status === 'completed') || selectedSources.size === 0}
                className="px-3 py-1 bg-accent text-bg text-[10px] font-bold rounded-sm hover:brightness-110 disabled:opacity-40 transition-all flex items-center gap-1.5"
              >
                <Play className="w-3 h-3" />
                Run All Steps
              </button>
            </div>
          </div>
          <div className="p-3 space-y-2">
            {pipelineSteps.map((step, idx) => (
              <div key={step.id} className={cn(
                "p-3 border rounded-sm transition-colors",
                step.status === 'completed' ? 'border-success/30 bg-success/5' :
                step.status === 'running' ? 'border-accent/30 bg-accent/5' :
                step.status === 'failed' ? 'border-danger/30 bg-danger/5' :
                'border-line/40 bg-surface/30'
              )}>
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
                    disabled={step.status === 'running' || step.status === 'completed' || selectedSources.size === 0}
                    className={cn(
                      "px-2.5 py-1 text-[10px] font-bold rounded-sm transition-all flex items-center gap-1",
                      step.status === 'completed' ? "bg-success/10 text-success border border-success/30" :
                      step.status === 'running' ? "bg-accent/10 text-accent border border-accent/30" :
                      "bg-surface border border-line text-ink/60 hover:bg-line/20"
                    )}
                  >
                    {step.status === 'completed' ? 'Completed' :
                     step.status === 'running' ? 'Running...' :
                     step.status === 'failed' ? 'Retry' : 'Run'}
                  </button>
                </div>
                {/* Step logs */}
                {step.log.length > 0 && (
                  <div className="mt-3 p-2 bg-black/40 border border-line/30 rounded max-h-20 overflow-y-auto font-mono text-[9px] leading-relaxed custom-scrollbar">
                    {step.log.slice(-10).map((line, li) => (
                      <div key={li} className={cn(
                        "whitespace-pre-wrap",
                        line.includes('[ERROR]') || line.includes('failed') ? 'text-danger' :
                        line.includes('[STDERR]') ? 'text-warning' : 'text-ink/50'
                      )}>
                        {line}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>

        {/* Info */}
        <div className="p-3 border border-line/30 bg-surface/20 rounded-sm">
          <div className="flex items-start gap-2 text-[10px] text-ink/40">
            <Terminal className="w-3 h-3 mt-0.5 shrink-0 text-accent" />
            <p>
              The <code className="text-accent">docs</code> technique generates NPC training data by extracting facts, commands, and prose from checked-in documentation. 
              Each source in the manifest defines curated questions and optional section hints to target specific content areas.
              Output is saved to <code className="text-accent">subjects/datasets/workflow_assistant/docs/</code>.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
