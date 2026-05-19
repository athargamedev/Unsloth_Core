import { motion, AnimatePresence } from 'motion/react';
import { cn } from '../lib/utils';
import type { Job } from '../api';
import { Card } from './Card';
import { Badge } from './Badge';
import { WorkflowVisualizer } from './WorkflowVisualizer';

interface OperationsMatrixProps {
  jobs: Job[];
  filteredJobs: Job[];
  selectedJobIds: string[];
  selectedJobId: string | null;
  activeFilter: 'all' | 'running';
  jobTypeFilter: string[];
  registryState: {
    workflowCount: number;
    autoSyncExternal: boolean;
  };
  isLoading?: boolean;
  uiError?: string | null;
  onSelectJob: (id: string) => void;
  onToggleJobSelection: (e: React.MouseEvent, id: string) => void;
  onSetActiveFilter: () => void;
  onToggleJobTypeFilter: (type: string) => void;
  onStopJob: (id: string) => void;
  onExportCsv: () => void;
  onOpenComparison: () => void;
  onManageJob: (id: string) => void;
  onDeleteJob: (id: string) => void;
  onViewLogs: (job: any) => void;
  onSyncJobs: (force?: boolean) => void | Promise<void>;
  onClearJobs: () => void | Promise<void>;
}

export const OperationsMatrix = ({
  jobs,
  filteredJobs,
  selectedJobIds,
  selectedJobId,
  activeFilter,
  jobTypeFilter,
  registryState,
  isLoading = false,
  uiError = null,
  onSelectJob,
  onToggleJobSelection,
  onSetActiveFilter,
  onToggleJobTypeFilter,
  onStopJob,
  onExportCsv,
  onOpenComparison,
  onManageJob,
  onDeleteJob,
  onViewLogs,
  onSyncJobs,
  onClearJobs,
}: OperationsMatrixProps) => {
  const selectedJob = selectedJobId ? jobs.find((j) => j.id === selectedJobId) : null;

  const getJobDetails = (job: Job) => {
    const args = job.command?.slice(1).join(' ') || '';
    const details: string[] = [];
    const npcKey =
      job.npcKey ||
      args.match(/subjects\/NPC_specs\/([A-Za-z0-9_\-]+)\.json/)?.[1] ||
      args.match(/subjects\/([A-Za-z0-9_\-]+)\.json/)?.[1] ||
      args.match(/outputs\/([A-Za-z0-9_\-]+)\//)?.[1] ||
      args.match(/exports\/([A-Za-z0-9_\-]+)\//)?.[1] ||
      '';
    const preset = args.match(/--preset\s+([^\s]+)/)?.[1];
    const technique = args.match(/--technique\s+([^\s]+)/)?.[1];
    const model = args.match(/--model\s+([^\s]+)/)?.[1] || args.match(/--base-model\s+([^\s]+)/)?.[1];

    if (job.commandId) details.push(job.commandId);
    if (npcKey) details.push(npcKey);
    if (preset) details.push(`preset:${preset}`);
    if (technique) details.push(`technique:${technique}`);
    if (model) details.push(`model:${model.split('/').pop()}`);

    return details.join(' · ');
  };

  const getActiveStageName = (job: Job) =>
    job.stages.find((stage) => stage.status === 'running')?.name ||
    job.stages.find((stage) => stage.status === 'failed' || stage.status === 'stopped')?.name ||
    '';

  return (
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
                onClick={onOpenComparison}
                className="px-2 py-0.5 bg-accent/20 border border-accent/40 text-accent text-[10px] font-bold rounded-sm animate-in zoom-in"
              >
                OPEN COMPARISON ({selectedJobIds.length})
              </button>
            )}
          </div>
          <div className="flex gap-2">
            <div className="flex items-center gap-2 rounded border border-line bg-panel/70 px-2 py-1">
              <span className="text-[12px] text-ink/45 font-bold uppercase tracking-wider">Types shown</span>
              {['Training', 'Dataset', 'Export', 'Evaluation'].map((t) => (
                <button
                  key={t}
                  onClick={() => onToggleJobTypeFilter(t)}
                  className={cn(
                    "px-2 py-1 rounded text-[12px] font-bold transition-all uppercase",
                    jobTypeFilter.includes(t)
                      ? "bg-accent/20 text-accent border border-accent/40"
                      : "bg-panel border border-line text-ink/40 hover:text-ink/60",
                  )}
                >
                  {t}
                </button>
              ))}
            </div>
            <div className="flex items-center gap-2 rounded border border-line bg-panel/70 px-2 py-1">
              <span className="text-[12px] text-ink/45 font-bold uppercase tracking-wider">Registry</span>
              <span className={cn(
                "px-2 py-1 rounded text-[11px] font-bold uppercase tracking-wider border",
                registryState.autoSyncExternal
                  ? "bg-success/10 text-success border-success/30"
                  : "bg-warning/10 text-warning border-warning/30",
              )}>
                {registryState.autoSyncExternal ? 'Auto-sync on' : 'Auto-sync paused'}
              </span>
              <span className="text-[12px] text-ink/40 font-mono">{registryState.workflowCount} workflows</span>
            </div>
            <button
              onClick={() => onSyncJobs(!registryState.autoSyncExternal)}
              className="px-2 py-1 bg-panel border border-line text-[10px] text-ink/60 rounded hover:bg-white/5 transition-colors"
              title={registryState.autoSyncExternal ? 'Refresh job snapshot' : 'Re-enable auto-sync and refresh external jobs'}
            >
              {registryState.autoSyncExternal ? 'Resync' : 'Resume & sync'}
            </button>
            <button
              onClick={onClearJobs}
              className="px-2 py-1 bg-panel border border-line text-[10px] text-danger rounded hover:bg-white/5 transition-colors"
              title="Clear all jobs, logs, and workflows from the matrix"
            >
              Clear Matrix
            </button>
            <button
              onClick={onSetActiveFilter}
              className={cn(
                "px-2 py-1 rounded text-[10px] font-bold transition-all",
                activeFilter === 'running'
                  ? "bg-accent text-bg border border-accent"
                  : "bg-panel border border-line text-ink/60 hover:bg-white/5",
              )}
            >
              {activeFilter === 'all' ? 'Showing All Jobs' : 'Showing Running Only'}
            </button>
            <button
              onClick={onExportCsv}
              className="px-2 py-1 bg-panel border border-line text-[10px] text-ink/60 rounded hover:bg-white/5 transition-colors"
            >
              Export CSV
            </button>
          </div>
        </div>

        <div className="flex-1 border border-line rounded-sm overflow-hidden bg-surface/30 backdrop-blur-sm">
          <div className="overflow-auto h-full">
            <table className="w-full text-left border-collapse table-fixed">
              <thead className="sticky top-0 z-10">
                <tr className="bg-header/80 backdrop-blur-md text-[10px] text-ink/50 uppercase">
                  <th className="p-3 border-b border-line font-bold tracking-wider w-8">
                    <div className="w-3 h-3 border border-line rounded-sm" />
                  </th>
                  <th className="p-3 border-b border-line font-bold tracking-wider w-1/3">Model / Version</th>
                  <th className="p-3 border-b border-line font-bold tracking-wider text-right">Loss</th>
                  <th className="p-3 border-b border-line font-bold tracking-wider text-right">Prog</th>
                  <th className="p-3 border-b border-line font-bold tracking-wider">Source</th>
                  <th className="p-3 border-b border-line font-bold tracking-wider">Status</th>
                  <th className="p-3 border-b border-line font-bold tracking-wider">W&B</th>
                  <th className="p-3 border-b border-line font-bold tracking-wider text-right">Action</th>
                </tr>
              </thead>
            <tbody className="text-[11px] font-mono divide-y divide-line/30">
                {isLoading ? (
                  Array.from({ length: 5 }).map((_, i) => (
                    <tr key={i} className="animate-shimmer opacity-20">
                      <td colSpan={8} className="p-4 h-12 bg-gradient-to-r from-transparent via-white/5 to-transparent" />
                    </tr>
                  ))
                ) : uiError ? (
                  <tr>
                    <td colSpan={8} className="p-6 text-center text-[12px] text-danger font-medium">
                      Failed to load jobs: {uiError}
                    </td>
                  </tr>
                ) : filteredJobs.length === 0 ? (
                  <tr>
                    <td colSpan={8} className="p-6 text-center text-[12px] text-ink/60">
                      {activeFilter === 'running'
                        ? 'No running jobs right now.'
                        : 'No jobs to display yet. Launch a dataset or training task to populate this table.'}
                    </td>
                  </tr>
                ) : filteredJobs.map((job) => (
                  <tr
                    key={job.id}
                    onClick={() => onSelectJob(job.id)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        onSelectJob(job.id);
                      }
                    }}
                    tabIndex={0}
                    role="button"
                    aria-label={`Select job ${job.name}`}
                    className={cn(
                      "hover:bg-accent/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/60 transition-all duration-300 cursor-pointer group",
                      job.status === 'running' ? "bg-accent/5" : "",
                      selectedJobId === job.id ? "bg-accent/20 border-l-2 border-accent" : "",
                      selectedJobIds.includes(job.id) ? "bg-accent/10" : "",
                    )}
                  >
                    <td className="p-3" onClick={(e) => onToggleJobSelection(e, job.id)}>
                      <div className={cn(
                        "w-3 h-3 border rounded-sm flex items-center justify-center transition-all duration-500",
                        selectedJobIds.includes(job.id) ? "bg-accent border-accent shadow-[0_0_8px_var(--accent-glow)]" : "border-line",
                      )}>
                        {selectedJobIds.includes(job.id) && <div className="w-1.5 h-1.5 bg-bg rounded-full" />}
                      </div>
                    </td>
                    <td className="p-3 font-bold text-ink-bright truncate group-hover:text-accent transition-colors">
                      <div className="min-w-0">
                        <div className="truncate">{job.name}</div>
                        {getJobDetails(job) && (
                          <div className="text-[9px] text-ink/45 truncate mt-0.5 font-mono">
                            {getJobDetails(job)}
                          </div>
                        )}
                      </div>
                    </td>
                    <td className={cn(
                      "p-3 text-right font-bold",
                      job.loss !== null && job.loss < 0.1 ? "text-success" : "text-warning",
                    )}>
                      {job.loss?.toFixed(3) || '--'}
                    </td>
                    <td className="p-3 text-right text-ink/70">
                      <div className="flex flex-col items-end gap-1">
                        <span>{job.progress}%</span>
                        <div className="w-12 h-1 bg-line rounded-full overflow-hidden">
                          <div className="h-full bg-accent transition-all duration-1000" style={{ width: `${job.progress}%` }} />
                        </div>
                        {getActiveStageName(job) && (
                          <span className="text-[9px] text-ink/40 truncate max-w-16">{getActiveStageName(job)}</span>
                        )}
                      </div>
                    </td>
                    <td className="p-3 text-ink/55 truncate uppercase text-[12px]">{job.type}</td>
                    <td className="p-3">
                      <Badge variant={job.status === 'completed' ? 'success' : job.status === 'running' ? 'warning' : job.status === 'failed' ? 'danger' : 'default'} className={cn(job.status === 'running' && "pulse-active")}>
                        {job.status}
                      </Badge>
                    </td>
                    <td className="p-3">
                      {job.wandbUrl ? (
                        <a
                          href={job.wandbUrl}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-accent hover:text-accent/80 underline text-[10px] font-bold tracking-tight flex items-center gap-1"
                          onClick={(e) => e.stopPropagation()}
                        >
                          <svg className="w-3 h-3" viewBox="0 0 24 24" fill="currentColor"><path d="M20.87 3.91l-4.49 1.7c-.42.16-.7.48-.7.91v11.27c0 .38.22.72.58.87l4.39 1.78c.63.25 1.22-.2 1.22-.87V4.78c0-.67-.59-1.12-1.22-.87zM3.13 3.91l4.49 1.7c.42.16.7.48.7.91v11.27c0 .38-.22.72-.58.87L3.35 20.44c-.63.25-1.22-.2-1.22-.87V4.78c0-.67.59-1.12 1.22-.87z"/></svg>
                          W&B
                        </a>
                      ) : (
                        <span className="text-ink/20 text-[9px]">--</span>
                      )}
                    </td>
                    <td className="p-3 text-right">
                      {job.status === 'running' ? (
                        <button onClick={(e) => { e.stopPropagation(); onStopJob(job.id); }} aria-label={`Stop job ${job.name}`} className="text-danger hover:text-danger/80 transition-colors uppercase text-[12px] font-bold tracking-tighter">Stop</button>
                      ) : (
                        <div className="flex justify-end gap-3">
                          <button
                            onClick={(e) => { e.stopPropagation(); onViewLogs(job); }}
                            aria-label={`View logs for job ${job.name}`}
                            className="text-ink/60 hover:text-ink transition-colors uppercase text-[12px] font-bold tracking-tighter flex items-center gap-1"
                          >
                            <svg className="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M4 6h16M4 12h16M4 18h7"/></svg>
                            Logs
                          </button>
                          <button
                            onClick={(e) => { e.stopPropagation(); onManageJob(job.id); }}
                            aria-label={`Compare job ${job.name}`}
                            className="text-accent hover:text-accent/80 transition-colors uppercase text-[12px] font-bold tracking-tighter"
                          >
                            Compare
                          </button>
                          <button
                            onClick={(e) => { e.stopPropagation(); onDeleteJob(job.id); }}
                            aria-label={`Clear job ${job.name}`}
                            className="text-ink/40 hover:text-danger transition-colors uppercase text-[12px] font-bold tracking-tighter"
                          >
                            Clear
                          </button>
                        </div>
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
        {selectedJob && (
          <motion.section
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="mx-4 mb-4"
          >
            <Card title={`Workflow Tracker: ${selectedJob.name}`} subtitle="PIPELINE_INSIGHTS">
              {selectedJob.wandbUrl && (
                <div className="mb-3 p-3 bg-accent/5 border border-accent/20 rounded-sm flex items-center gap-3">
                  <svg className="w-4 h-4 text-accent shrink-0" viewBox="0 0 24 24" fill="currentColor"><path d="M21.12 3.9l-4.67 1.77c-.33.12-.55.37-.55.7v11.26c0 .29.17.55.45.66l4.56 1.86c.66.26 1.27-.2 1.27-.9V4.8c0-.7-.61-1.16-1.27-.9zM3.37 4.8v14.2c0 .7.61 1.16 1.27.9l4.56-1.86c.28-.11.45-.37.45-.66V6.37c0-.33-.22-.58-.55-.7L4.43 3.9c-.66-.26-1.27.2-1.27.9zm7.43.07v14.26c0 .37.28.66.65.66.37 0 .65-.29.65-.66V4.87c0-.37-.28-.66-.65-.66-.37 0-.65.29-.65.66z"/></svg>
                  <div className="flex-1 min-w-0">
                    <span className="text-[10px] font-bold text-ink-bright uppercase tracking-wider">W&B Run Active</span>
                    <a
                      href={selectedJob.wandbUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="block text-[11px] text-accent hover:text-accent/80 underline truncate mt-0.5 font-mono"
                    >
                      {selectedJob.wandbUrl}
                    </a>
                  </div>
                </div>
              )}
              <WorkflowVisualizer stages={selectedJob.stages} />
              <div className="flex gap-4 mt-2">
                {selectedJob.stages.find(s => s.status === 'running' || s.status === 'completed' && s.logs.length > 0) && (
                  <div className="flex-1 p-2 bg-black/20 rounded border border-line/30 text-[10px] mono-label">
                    <span className="text-accent underline font-bold mb-1 block">Active Stage Logs:</span>
                    {selectedJob.stages.find(s => s.status === 'running')?.logs.map((l, i) => <div key={i} className="text-ink/60">• {l}</div>) ||
                     selectedJob.stages.find(s => s.status === 'completed')?.logs.map((l, i) => <div key={i} className="text-success/60">• {l}</div>)}
                  </div>
                )}
              </div>
            </Card>
          </motion.section>
        )}
      </AnimatePresence>
    </motion.div>
  );
};
