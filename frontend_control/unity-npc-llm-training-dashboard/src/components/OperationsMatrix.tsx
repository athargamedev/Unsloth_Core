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
  onSelectJob: (id: string) => void;
  onToggleJobSelection: (e: React.MouseEvent, id: string) => void;
  onSetActiveFilter: () => void;
  onStopJob: (id: string) => void;
  onExportCsv: () => void;
  onOpenComparison: () => void;
  onManageJob: (id: string) => void;
}

export const OperationsMatrix = ({
  jobs,
  filteredJobs,
  selectedJobIds,
  selectedJobId,
  activeFilter,
  onSelectJob,
  onToggleJobSelection,
  onSetActiveFilter,
  onStopJob,
  onExportCsv,
  onOpenComparison,
  onManageJob,
}: OperationsMatrixProps) => {
  const selectedJob = selectedJobId ? jobs.find((j) => j.id === selectedJobId) : null;

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
            <button
              onClick={onSetActiveFilter}
              className={cn(
                "px-2 py-1 rounded text-[10px] font-bold transition-all",
                activeFilter === 'running'
                  ? "bg-accent text-bg border border-accent"
                  : "bg-panel border border-line text-ink/60 hover:bg-white/5",
              )}
            >
              Filter: {activeFilter === 'all' ? 'Active' : 'All'}
            </button>
            <button
              onClick={onExportCsv}
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
                    onClick={() => onSelectJob(job.id)}
                    className={cn(
                      "hover:bg-accent/5 transition-colors cursor-pointer",
                      job.status === 'running' ? "bg-accent/5" : "",
                      selectedJobId === job.id ? "bg-accent/20 border-l-2 border-accent" : "",
                      selectedJobIds.includes(job.id) ? "bg-accent/10" : "",
                    )}
                  >
                    <td className="p-2" onClick={(e) => onToggleJobSelection(e, job.id)}>
                      <div className={cn(
                        "w-3 h-3 border rounded-sm flex items-center justify-center transition-colors",
                        selectedJobIds.includes(job.id) ? "bg-accent border-accent" : "border-line",
                      )}>
                        {selectedJobIds.includes(job.id) && <div className="w-1.5 h-1.5 bg-bg rounded-full" />}
                      </div>
                    </td>
                    <td className="p-2 font-bold text-ink-bright truncate">{job.name}</td>
                    <td className={cn(
                      "p-2 text-right font-bold",
                      job.loss !== null && job.loss < 0.1 ? "text-success" : "text-warning",
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
                        <button onClick={(e) => { e.stopPropagation(); onStopJob(job.id); }} className="text-danger hover:underline uppercase text-[9px] font-bold">Stop</button>
                      ) : (
                        <button
                          onClick={(e) => { e.stopPropagation(); onManageJob(job.id); }}
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
        {selectedJob && (
          <motion.section
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="mx-4 mb-4"
          >
            <Card title={`Workflow Tracker: ${selectedJob.name}`} subtitle="PIPELINE_INSIGHTS">
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
