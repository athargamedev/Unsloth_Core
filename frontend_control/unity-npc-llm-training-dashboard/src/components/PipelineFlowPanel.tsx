import { useState, useEffect } from 'react';
import { fetchJson } from '../api';
import type { PipelineState, PipelineNpcState, Subject, Dataset, RunArtifact, ExportArtifact, PipelineRunsResponse, PipelineRunDetail, PipelineRunRecord } from '../api';

// Each stage in the pipeline lifecycle
interface PipelineStage {
  id: string;
  label: string;
  completed: boolean;
  actionable: boolean;
  description: string;
}

function computeStages(npcKey: string, state: PipelineNpcState | undefined, subjects: Subject[], datasets: Dataset[], runs: RunArtifact[], exports: ExportArtifact[]): PipelineStage[] {
  const hasSpec = subjects.some(s => s.id === npcKey);
  const hasDataset = datasets.some(d => d.id === npcKey && d.versions.length > 0);
  const hasRun = runs.some(r => r.npcKey === npcKey);
  const hasExport = exports.some(e => e.npcKey === npcKey);
  const hasEval = state?.eval_report ? true : false;
  const hasFeedback = state?.status ? true : false;

  return [
    { id: 'spec', label: 'Spec', completed: hasSpec, actionable: !hasSpec, description: 'Subject JSON + ref doc' },
    { id: 'dataset', label: 'Dataset', completed: hasDataset, actionable: !hasDataset && hasSpec, description: 'Onyx-generated Q&A pairs' },
    { id: 'train', label: 'Train', completed: hasRun, actionable: !hasRun && hasDataset, description: 'LoRA fine-tuning' },
    { id: 'export', label: 'Export', completed: hasExport, actionable: !hasExport && hasRun, description: 'Adapter GGUF' },
    { id: 'eval', label: 'Eval', completed: hasEval, actionable: !hasEval && hasExport, description: 'Baseline comparison' },
    { id: 'feedback', label: 'Feedback', completed: hasFeedback, actionable: !hasFeedback && hasEval, description: 'Self-improvement loop' },
  ];
}

export const PipelineFlowPanel = ({
  subjects, datasets, runs, exportArtifacts,
}: {
  subjects: Subject[];
  datasets: Dataset[];
  runs: RunArtifact[];
  exportArtifacts: ExportArtifact[];
}) => {
  const [pipelineState, setPipelineState] = useState<PipelineState | null>(null);
  const [loading, setLoading] = useState(true);
  const [pipelineRuns, setPipelineRuns] = useState<PipelineRunRecord[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [selectedRunDetail, setSelectedRunDetail] = useState<PipelineRunDetail | null>(null);

  useEffect(() => {
    const load = async () => {
      try {
        const state = await fetchJson<PipelineState>('/api/pipeline-state');
        setPipelineState(state);
      } catch {
        setPipelineState({});
      }

      try {
        const response = await fetchJson<PipelineRunsResponse>('/api/pipeline/runs?limit=24');
        setPipelineRuns(response.runs ?? []);
        const firstRunId = response.runs?.[0]?.run_id ?? null;
        setSelectedRunId((current) => current ?? firstRunId);
      } catch {
        setPipelineRuns([]);
      }

      setLoading(false);
    };
    load();
    const interval = setInterval(load, 15000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    if (!selectedRunId) {
      setSelectedRunDetail(null);
      return;
    }
    const loadRunDetail = async () => {
      try {
        const detail = await fetchJson<PipelineRunDetail>(`/api/pipeline/runs/${encodeURIComponent(selectedRunId)}`);
        setSelectedRunDetail(detail);
      } catch {
        setSelectedRunDetail(null);
      }
    };
    loadRunDetail();
  }, [selectedRunId]);

  // Collect all NPC keys from subjects, datasets, runs, exports, and pipeline state
  const allNpcKeys = new Set<string>();
  subjects.forEach(s => allNpcKeys.add(s.id));
  datasets.forEach(d => allNpcKeys.add(d.id));
  runs.forEach(r => allNpcKeys.add(r.npcKey));
  exportArtifacts.forEach(e => allNpcKeys.add(e.npcKey));
  if (pipelineState) Object.keys(pipelineState).forEach(k => allNpcKeys.add(k));

  const sortedKeys = Array.from(allNpcKeys).sort();

  const stageColor = (completed: boolean, actionable: boolean) => {
    if (completed) return 'bg-success';
    if (actionable) return 'bg-warning/70';
    return 'bg-line/40';
  };

  const stageLabelColor = (completed: boolean, actionable: boolean) => {
    if (completed) return 'text-success';
    if (actionable) return 'text-warning';
    return 'text-ink/30';
  };

  const statusBadge = (state: PipelineNpcState | undefined) => {
    if (!state) return { label: 'Draft', color: 'bg-line/40 text-ink/40' };
    switch (state.status) {
      case 'healthy': return { label: 'Healthy', color: 'bg-success/20 text-success border border-success/30' };
      case 'regenerated': return { label: 'Improved', color: 'bg-accent/20 text-accent border border-accent/30' };
      case 'regeneration_failed': return { label: 'Failed', color: 'bg-danger/20 text-danger border border-danger/30' };
      default: return { label: state.status, color: 'bg-warning/20 text-warning border border-warning/30' };
    }
  };

  if (loading) {
    return <div className="flex-1 flex items-center justify-center text-[12px] text-ink/40">Loading pipeline state...</div>;
  }

  return (
    <div className="flex-1 overflow-auto p-4 space-y-4 custom-scrollbar">
      <div className="flex items-center justify-between mb-2">
        <div>
          <h3 className="text-xs font-bold text-ink-bright uppercase tracking-widest">NPC Pipeline Lifecycle</h3>
          <p className="text-[10px] text-ink/40">Monitor and advance each NPC through the generation pipeline</p>
        </div>
        <div className="flex gap-4 text-[10px]">
          <span className="flex items-center gap-1"><span className="w-2 h-2 rounded bg-success" /> Done</span>
          <span className="flex items-center gap-1"><span className="w-2 h-2 rounded bg-warning/70" /> Ready</span>
          <span className="flex items-center gap-1"><span className="w-2 h-2 rounded bg-line/40" /> Pending</span>
        </div>
      </div>

      {sortedKeys.length === 0 && (
        <div className="text-center py-8 text-ink/40 text-[12px]">
          No NPC subjects found. Create a subject spec under <code className="text-accent">subjects/</code> to get started.
        </div>
      )}

      {sortedKeys.map((npcKey) => {
        const state = pipelineState?.[npcKey];
        const stages = computeStages(npcKey, state, subjects, datasets, runs, exportArtifacts);
        const badge = statusBadge(state);

        return (
          <div key={npcKey} className="bg-surface border border-line rounded-sm p-4 hover:border-accent/30 transition-colors">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-3">
                <div className="w-8 h-8 rounded bg-accent/20 flex items-center justify-center text-accent font-bold text-sm font-mono">
                  {npcKey.charAt(0).toUpperCase()}
                </div>
                <div>
                  <h4 className="text-sm font-bold text-ink-bright font-mono">{npcKey}</h4>
                  <span className={`text-[10px] px-1.5 py-0.5 rounded font-mono ${badge.color}`}>
                    {badge.label}
                  </span>
                </div>
              </div>
              {state?.latest_win_rate !== undefined && (
                <div className="text-right">
                  <span className="text-[10px] text-ink/40 uppercase">Win Rate</span>
                  <div className={`text-lg font-bold font-mono ${(state.latest_win_rate || 0) >= 0.5 ? 'text-success' : 'text-warning'}`}>
                    {(state.latest_win_rate * 100).toFixed(0)}%
                  </div>
                </div>
              )}
            </div>

            {/* Pipeline stages */}
            <div className="flex items-center gap-1">
              {stages.map((stage, idx) => (
                <div key={stage.id} className="flex-1 flex flex-col items-center">
                  <div className="flex items-center w-full">
                    <div className={`h-2 w-full rounded-l-sm ${stageColor(stage.completed, stage.actionable)}`} />
                    <div className={`w-4 h-4 rounded-full border-2 flex items-center justify-center -mx-2 z-10 ${stage.completed ? 'bg-success border-success' : stage.actionable ? 'bg-warning/20 border-warning' : 'bg-line/20 border-line'}`}>
                      {stage.completed && <span className="text-bg text-[8px] font-bold">✓</span>}
                    </div>
                    <div className={`h-2 w-full rounded-r-sm ${stageColor(stage.completed, stage.actionable)}`} />
                  </div>
                  <span className={`text-[9px] font-bold uppercase mt-1 ${stageLabelColor(stage.completed, stage.actionable)}`}>
                    {stage.label}
                  </span>
                  <span className="text-[7px] text-ink/30 leading-tight text-center max-w-[60px]">{stage.description}</span>
                </div>
              ))}
            </div>

            {/* State details */}
            {state && (
              <div className="mt-3 pt-3 border-t border-line/30 grid grid-cols-3 md:grid-cols-5 gap-2 text-[9px]">
                {state.dataset && <div><span className="text-ink/40">Dataset: </span><span className="text-ink/70">{state.dataset}</span></div>}
                {state.training && <div><span className="text-ink/40">Training: </span><span className="text-ink/70">{state.training}</span></div>}
                {state.gguf_adapter && <div><span className="text-ink/40">GGUF: </span><span className="text-ink/70 truncate block max-w-[140px]">{state.gguf_adapter}</span></div>}
                {state.gguf_validation && <div><span className="text-ink/40">Valid: </span><span className={state.gguf_validation.includes('PASS') ? 'text-success' : 'text-danger'}>{state.gguf_validation}</span></div>}
                {state.weak_concepts_count !== undefined && <div><span className="text-ink/40">Weak: </span><span className="text-warning">{state.weak_concepts_count} concepts</span></div>}
              </div>
            )}

            {/* Action button for next stage */}
            {(() => {
              const nextActionable = stages.find(s => s.actionable);
              if (!nextActionable) return null;
              return (
                <div className="mt-2 pt-2 border-t border-line/20">
                  <button
                    onClick={() => {
                      const event = new CustomEvent('navigate-pipeline-action', { detail: { npcKey, stage: nextActionable.id } });
                      window.dispatchEvent(event);
                    }}
                    className="px-3 py-1 bg-accent text-bg text-[10px] font-bold rounded-sm hover:brightness-110 transition-colors"
                  >
                    Next: {nextActionable.label} →
                  </button>
                </div>
              );
            })()}
          </div>
        );
      })}

      <div className="bg-surface border border-line rounded-sm p-4">
        <div className="flex items-center justify-between mb-3">
          <div>
            <h4 className="text-sm font-bold text-ink-bright uppercase tracking-widest">Pipeline History</h4>
            <p className="text-[10px] text-ink/40">Unified run index and per-run artifacts from .pipeline/runs.jsonl</p>
          </div>
          <span className="text-[10px] text-ink/40 font-mono">{pipelineRuns.length} runs</span>
        </div>

        <div className="grid grid-cols-1 xl:grid-cols-[1.3fr_1fr] gap-3 min-h-[260px]">
          <div className="border border-line/40 rounded-sm overflow-hidden">
            <div className="max-h-[220px] overflow-auto custom-scrollbar">
              {pipelineRuns.length > 0 ? (
                pipelineRuns.map((run) => {
                  const isSelected = run.run_id === selectedRunId;
                  return (
                    <button
                      key={`${run.run_id}-${run.event}-${run.ts}`}
                      onClick={() => run.run_id && setSelectedRunId(run.run_id)}
                      className={`w-full text-left px-3 py-2 border-b border-line/20 hover:bg-white/5 transition-colors ${isSelected ? 'bg-accent/10' : ''}`}
                    >
                      <div className="flex items-center justify-between gap-3">
                        <div className="min-w-0">
                          <div className="text-[10px] font-mono text-ink-bright truncate">{run.run_id || 'unknown-run'}</div>
                          <div className="text-[9px] text-ink/40 font-mono truncate">{run.npc_key || 'unknown'} · {run.stage || 'stage?'} · {run.event || 'event?'}</div>
                        </div>
                        <div className="text-[9px] text-right text-ink/50 font-mono shrink-0">
                          {run.status || run.event || '—'}
                          <div>{run.ts ? new Date(run.ts).toLocaleString() : ''}</div>
                        </div>
                      </div>
                    </button>
                  );
                })
              ) : (
                <div className="p-4 text-[11px] text-ink/40">No pipeline runs found yet.</div>
              )}
            </div>
          </div>

          <div className="border border-line/40 rounded-sm p-3 text-[10px] text-ink/70 space-y-2 bg-black/10">
            {selectedRunDetail ? (
              <>
                <div className="font-mono text-ink-bright break-all">{String(selectedRunDetail.run.run_id || selectedRunId || 'run')}</div>
                <div className="grid grid-cols-2 gap-2">
                  <div><span className="text-ink/40">Events:</span> {selectedRunDetail.events.length}</div>
                  <div><span className="text-ink/40">Hooks:</span> {selectedRunDetail.hooks.length}</div>
                  <div><span className="text-ink/40">Log lines:</span> {selectedRunDetail.log.length}</div>
                  <div><span className="text-ink/40">NPC:</span> {String(selectedRunDetail.run.npc_key || '—')}</div>
                </div>
                <div>
                  <div className="text-[9px] uppercase tracking-widest text-ink/40 mb-1">Latest Log</div>
                  <div className="max-h-[120px] overflow-auto custom-scrollbar font-mono text-[9px] bg-black/20 rounded p-2 space-y-1">
                    {selectedRunDetail.log.slice(-8).map((line, idx) => (
                      <div key={idx} className="whitespace-pre-wrap break-all">{line}</div>
                    ))}
                  </div>
                </div>
              </>
            ) : (
              <div className="text-ink/40">Select a run to inspect its metadata, hook timeline, and structured log lines.</div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
