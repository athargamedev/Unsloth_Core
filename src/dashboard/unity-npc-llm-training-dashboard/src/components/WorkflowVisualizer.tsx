import { cn } from '../lib/utils';
import type { Stage } from '../api';

interface WorkflowVisualizerProps {
  stages: Stage[];
}

export const WorkflowVisualizer = ({ stages }: WorkflowVisualizerProps) => (
  <div className="flex items-center w-full gap-2 p-2">
    {stages.map((stage, i) => (
      <div key={i} className="flex-1 flex flex-col gap-2 relative">
        <div className="flex items-center gap-2">
          <div className={cn(
            "w-2.5 h-2.5 rounded-full z-10",
            stage.status === 'completed' ? "bg-success glow-blue" :
            stage.status === 'running' ? "bg-warning animate-pulse" :
            stage.status === 'failed' ? "bg-danger ring-2 ring-danger/40" :
            stage.status === 'stopped' ? "bg-ink/30 ring-2 ring-ink/20" : "bg-line"
          )} />
          <span className={cn(
            "text-[9px] font-bold uppercase tracking-widest truncate",
            stage.status === 'running' ? "text-warning" :
            stage.status === 'completed' ? "text-ink" :
            stage.status === 'failed' ? "text-danger" :
            stage.status === 'stopped' ? "text-ink/30" : "text-ink/30"
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
