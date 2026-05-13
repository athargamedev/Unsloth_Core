import { motion } from 'motion/react';
import { Shield, Download, Database, CheckCircle, XCircle } from 'lucide-react';
import { cn } from '../lib/utils';
import { Card } from './Card';
import { Badge } from './Badge';

interface Subject {
  id: string;
  path: string;
}

interface DatasetVersion {
  tag: string;
  entries: number;
}

interface Dataset {
  id: string;
  name: string;
  versions: DatasetVersion[];
}

interface RunArtifact {
  id: string;
  npcKey: string;
  updatedAt: string;
}

interface ExportArtifact {
  npcKey: string;
  file: string;
  updatedAt: string;
}

interface Job {
  id: string;
  name: string;
  status: string;
  type: string;
  npcKey?: string;
}

interface NpcOverviewProps {
  subjects: Subject[];
  datasets: Dataset[];
  runs: RunArtifact[];
  exportArtifacts: ExportArtifact[];
  jobs: Job[];
}

const TECHNIQUE_LABELS: Record<string, string> = {
  notebooklm: 'NotebookLM',
  ollama: 'Ollama',
  template: 'Template',
};

export const NpcOverview = ({
  subjects,
  datasets,
  runs,
  exportArtifacts,
  jobs,
}: NpcOverviewProps) => {
  const subjectKeys = new Set(subjects.map((s) => s.id));
  const npcKeys = Array.from(subjectKeys);

  // Identify all NPC keys that appear in any data source
  const allNpcKeys = Array.from(
    new Set([
      ...npcKeys,
      ...datasets.map((d) => d.id),
      ...runs.map((r) => r.npcKey),
      ...exportArtifacts.map((e) => e.npcKey),
    ]),
  ).sort();

  if (allNpcKeys.length === 0) {
    return null;
  }

  return (
    <section className="mb-4">
      <div className="flex items-center gap-3 mb-3">
        <Database className="w-3.5 h-3.5 text-accent" />
        <h3 className="text-xs font-bold text-ink-bright uppercase tracking-widest">
          NPC Project Overview
        </h3>
        <span className="text-[10px] text-ink/40 font-mono">
          {allNpcKeys.length} NPCs
        </span>
      </div>

      <motion.div
        initial="hidden"
        animate="visible"
        variants={{
          visible: { transition: { staggerChildren: 0.05 } },
        }}
        className="grid grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3"
      >
        {allNpcKeys.map((npcKey) => {
          const subject = subjects.find((s) => s.id === npcKey);
          const ds = datasets.find((d) => d.id === npcKey);
          const hasRun = runs.some((r) => r.npcKey === npcKey);
          const hasExport = exportArtifacts.some((e) => e.npcKey === npcKey);
          const runningJobs = jobs.filter(
            (j) => j.npcKey === npcKey && j.status === 'running',
          );
          const displayName = ds?.name || subject?.id || npcKey;

          // Determine technique badges
          const techniqueEntries = new Map<string, number>();
          if (ds) {
            for (const v of ds.versions) {
              techniqueEntries.set(v.tag, v.entries);
            }
          }

          return (
            <motion.div
              key={npcKey}
              variants={{
                hidden: { opacity: 0, y: 12 },
                visible: { opacity: 1, y: 0 },
              }}
              whileHover={{ scale: 1.02 }}
              className="bg-surface/30 backdrop-blur-sm border border-line rounded p-3 cursor-pointer transition-all duration-300 hover:border-accent/50 hover:shadow-[0_0_12px_var(--accent-glow)] group"
              onClick={() => {
                // Navigate to Dataset Factory tab — dispatch a custom event
                window.dispatchEvent(
                  new CustomEvent('navigate-tab', { detail: { tab: 'datasets', npcKey } }),
                );
              }}
            >
              {/* NPC Name */}
              <div className="flex items-center justify-between mb-2">
                <h4 className="text-[11px] font-bold text-ink-bright truncate group-hover:text-accent transition-colors">
                  {displayName}
                </h4>
                {runningJobs.length > 0 && (
                  <span className="w-2 h-2 rounded-full bg-warning animate-pulse shrink-0" />
                )}
              </div>

              {/* Dataset Badges */}
              <div className="flex flex-wrap gap-1.5 mb-2">
                {Object.keys(TECHNIQUE_LABELS).map((tag) => {
                  const count = techniqueEntries.get(tag) ?? 0;
                  return (
                    <Badge
                      key={tag}
                      variant={count > 0 ? 'success' : 'default'}
                      className={cn(
                        'text-[8px] px-1 py-0.5',
                        count === 0 && 'opacity-30',
                      )}
                    >
                      {TECHNIQUE_LABELS[tag]}: {count}
                    </Badge>
                  );
                })}
                {/* Show any custom technique not in our known set */}
                {ds &&
                  ds.versions
                    .filter((v) => !TECHNIQUE_LABELS[v.tag])
                    .map((v) => (
                      <Badge
                        key={v.tag}
                        variant="success"
                        className="text-[8px] px-1 py-0.5"
                      >
                        {v.tag}: {v.entries}
                      </Badge>
                    ))}
              </div>

              {/* Status indicators */}
              <div className="flex items-center gap-3 text-[10px]">
                <div className="flex items-center gap-1">
                  {hasRun ? (
                    <CheckCircle className="w-3 h-3 text-success" />
                  ) : (
                    <XCircle className="w-3 h-3 text-ink/30" />
                  )}
                  <span
                    className={cn(
                      'font-medium',
                      hasRun ? 'text-success' : 'text-ink/40',
                    )}
                  >
                    {hasRun ? 'Trained' : 'Not trained'}
                  </span>
                </div>
                <div className="flex items-center gap-1">
                  {hasExport ? (
                    <Shield className="w-3 h-3 text-accent" />
                  ) : (
                    <XCircle className="w-3 h-3 text-ink/30" />
                  )}
                  <span
                    className={cn(
                      'font-medium',
                      hasExport ? 'text-accent' : 'text-ink/40',
                    )}
                  >
                    {hasExport ? 'Exported' : 'Not exported'}
                  </span>
                </div>
              </div>

              {/* Click hint */}
              <div className="mt-2 pt-1.5 border-t border-line/20 opacity-0 group-hover:opacity-100 transition-opacity">
                <span className="text-[8px] text-accent/60 uppercase tracking-wider font-bold">
                  Click to view dataset →
                </span>
              </div>
            </motion.div>
          );
        })}
      </motion.div>
    </section>
  );
};
