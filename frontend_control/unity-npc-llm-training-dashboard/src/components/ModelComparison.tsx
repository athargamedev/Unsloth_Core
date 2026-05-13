import { motion } from 'motion/react';
import { Layers, XCircle, FileText } from 'lucide-react';
import { cn } from '../lib/utils';
import { Card } from './Card';
import type { ExportArtifact, Job, RunArtifact } from '../api';

interface ModelComparisonProps {
  selectedJobIds: string[];
  jobs: Job[];
  runs: RunArtifact[];
  exportArtifacts: ExportArtifact[];
  onToggleJobSelection: (e: React.MouseEvent, id: string) => void;
  onClearSelection: () => void;
  onNavigateTo: (tab: 'overview' | 'training' | 'datasets' | 'compare' | 'analytics' | 'commands') => void;
}

export const ModelComparison = ({
  selectedJobIds,
  jobs,
  runs,
  exportArtifacts,
  onToggleJobSelection,
  onClearSelection,
  onNavigateTo,
}: ModelComparisonProps) => {
  const handleViewReports = () => {
    onNavigateTo('commands');
  };

  const getJobNpcKey = (job: Job) => job.npcKey || job.name.match(/\(([^)]+)\)/)?.[1] || '';

  const handleViewArtifacts = (job: Job) => {
    const npcKey = getJobNpcKey(job);
    if (!npcKey) return;
    onNavigateTo('datasets');
    window.dispatchEvent(new CustomEvent('navigate-tab', { detail: { tab: 'datasets', npcKey } }));
  };

  return (
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
            onClick={onClearSelection}
            className="px-3 py-1 bg-panel border border-line text-[10px] text-ink/60 rounded uppercase"
          >
            Clear Selection
          </button>
          <button
            onClick={handleViewReports}
            disabled={selectedJobIds.length === 0}
            className="px-3 py-1 bg-accent text-bg text-[10px] font-bold rounded uppercase disabled:opacity-40 hover:brightness-110 transition-all"
          >
            View Reports
          </button>
        </div>
      </div>

      {selectedJobIds.length === 0 ? (
        <div className="flex-1 flex flex-col items-center justify-center border-2 border-dashed border-line rounded-lg text-ink/30 italic">
          <Layers className="w-12 h-12 mb-4 opacity-20" />
          <p className="text-sm">No models selected for comparison.</p>
          <button onClick={() => onNavigateTo('overview')} className="mt-4 text-accent text-xs font-bold underline">Go back to Matrix</button>
        </div>
      ) : (
        <div className="flex-1 overflow-x-auto overflow-y-hidden custom-scrollbar pb-4">
          <div className="flex gap-4 h-full min-w-max">
            {selectedJobIds.map((id) => {
              const job = jobs.find((j) => j.id === id);
              if (!job) return null;
              const npcKey = getJobNpcKey(job);
              const jobRuns = npcKey ? runs.filter((run) => run.npcKey === npcKey) : [];
              const jobExports = npcKey ? exportArtifacts.filter((artifact) => artifact.npcKey === npcKey) : [];
              const hasArtifactMetadata = jobRuns.length > 0 || jobExports.length > 0;
              return (
                <div key={job.id} className="w-[320px] bg-surface border border-line rounded-sm flex flex-col overflow-hidden animate-in fade-in slide-in-from-right-4">
                  <div className="p-4 bg-header border-b border-line flex justify-between items-center">
                    <div className="truncate">
                      <h4 className="text-sm font-bold text-ink-bright truncate">{job.name}</h4>
                      <p className="text-[10px] opacity-40 font-mono italic">#{job.id}</p>
                    </div>
                    <button onClick={(e) => onToggleJobSelection(e, job.id)} className="text-ink/20 hover:text-danger p-1">
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
                          <span className="text-ink/40">Runner</span>
                          <span className="text-ink-bright font-mono">{job.status === 'running' ? 'Active local process' : 'Recorded job'}</span>
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
                              s.status === 'failed' ? "bg-danger" :
                              s.status === 'stopped' ? "bg-ink/30" : "bg-line",
                            )} />
                            <span className={cn(
                              s.status === 'failed' ? "text-danger" :
                              s.status === 'stopped' ? "text-ink/30" :
                              s.status === 'pending' ? "text-ink/20" : "text-ink/70",
                            )}>{s.name}</span>
                          </div>
                        ))}
                      </div>
                    </div>

                    <div className="pt-4 border-t border-line/20 space-y-2">
                      <span className="text-[9px] uppercase font-bold text-ink/30 tracking-widest block">Artifacts</span>
                      {hasArtifactMetadata ? (
                        <div className="space-y-1 text-[10px] font-mono">
                          {jobRuns.slice(0, 2).map((run) => (
                            <div key={run.id} className="truncate text-ink/60">Run: {run.id}</div>
                          ))}
                          {jobExports.slice(0, 2).map((artifact) => (
                            <div key={artifact.file} className="truncate text-ink/60">GGUF: {artifact.file}</div>
                          ))}
                        </div>
                      ) : (
                        <div className="text-[10px] text-ink/35">No run/export artifact metadata recorded for this job.</div>
                      )}
                      <button
                        onClick={() => handleViewArtifacts(job)}
                        disabled={!hasArtifactMetadata}
                        title={hasArtifactMetadata ? 'Open artifact summary in Dataset Factory' : 'No artifact metadata is available for this job'}
                        className="w-full flex items-center justify-center gap-2 py-2 bg-accent/10 border border-accent/20 text-accent text-[10px] font-bold rounded uppercase hover:bg-accent/20 transition-colors disabled:opacity-35 disabled:cursor-not-allowed"
                      >
                        <FileText className="w-3 h-3" />
                        {hasArtifactMetadata ? 'Open Artifacts Summary' : 'No Artifacts Recorded'}
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
  );
};
