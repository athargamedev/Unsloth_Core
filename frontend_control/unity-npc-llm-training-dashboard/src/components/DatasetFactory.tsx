import { motion } from 'motion/react';
import { ExternalLink } from 'lucide-react';
import { Card } from './Card';
import { Badge } from './Badge';
import type { Dataset, RunArtifact, ExportArtifact, TrainingConfig } from '../api';

interface DatasetFactoryProps {
  datasets: Dataset[];
  runs: RunArtifact[];
  exportArtifacts: ExportArtifact[];
  trainingConfig: TrainingConfig;
  onGenerateDataset: () => Promise<void>;
}

export const DatasetFactory = ({
  datasets,
  runs,
  exportArtifacts,
  trainingConfig,
  onGenerateDataset,
}: DatasetFactoryProps) => {
  const intentDistribution = [
    { label: 'Informational', val: 65 },
    { label: 'Transactional', val: 20 },
    { label: 'Hostile', val: 10 },
    { label: 'Fearful', val: 5 },
  ];

  return (
    <motion.div
      key="datasets"
      initial={{ opacity: 0, x: 10 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: -10 }}
      className="flex-1 overflow-hidden p-4 flex flex-col gap-4"
    >
      <div className="flex justify-between items-end">
        <h3 className="text-xs font-bold text-ink-bright uppercase tracking-widest">Dataset Versioning & Control</h3>
        <button
          onClick={onGenerateDataset}
          className="px-3 py-1 bg-accent text-bg text-[10px] font-bold rounded-sm uppercase tracking-tighter hover:brightness-110 active:scale-95 transition-all"
        >
          Generate from Spec
        </button>
      </div>

      <div className="grid grid-cols-2 gap-4 flex-1 overflow-hidden">
        <Card title="Available Datasets" subtitle="LOCAL_FLAT_DB" className="flex-1">
          <div className="space-y-4">
            {datasets.map((ds) => (
              <div key={ds.id} className="p-3 bg-panel border border-line rounded flex flex-col gap-3 group hover:border-accent transition-colors">
                <div className="flex justify-between items-start">
                  <div>
                    <h4 className="text-sm font-bold text-ink-bright">{ds.name}</h4>
                    <p className="text-[10px] text-ink/40 font-mono">ID: {ds.id}</p>
                  </div>
                  <Badge variant="success">SYNCED</Badge>
                </div>

                <div className="space-y-1">
                  <span className="text-[9px] uppercase font-bold text-ink/30 tracking-widest">Version History</span>
                  <div className="space-y-1 max-h-32 overflow-y-auto custom-scrollbar pr-1">
                    {ds.versions.map((v, i) => (
                      <div key={i} className="flex justify-between items-center p-1.5 bg-bg/50 border border-line/20 rounded-sm text-[10px]">
                        <div className="flex gap-2 items-center">
                          <span className="font-bold text-accent">{v.tag}</span>
                          <span className="text-ink/40">• {v.entries} pairs</span>
                        </div>
                        <div className="flex gap-2">
                          <button className="text-accent hover:underline uppercase text-[8px] font-bold">Select</button>
                          <button className="text-ink/20 hover:text-ink/60 uppercase text-[8px] font-bold">Details</button>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="flex gap-2 mt-auto pt-2 border-t border-line/20">
                  <button className="flex-1 py-1.5 bg-accent/5 border border-accent/20 text-accent text-[10px] font-bold rounded uppercase hover:bg-accent/10 transition-colors">Compare v1 vs v2</button>
                  <button className="p-1.5 bg-line/20 border border-line/30 rounded hover:bg-line/40 transition-colors">
                    <ExternalLink className="w-3 h-3 text-ink/40" />
                  </button>
                </div>
              </div>
            ))}
            {datasets.length === 0 && <div className="text-[10px] text-ink/40">No datasets found in datasets/*</div>}
          </div>
        </Card>

        <Card title="Dataset Analytics" subtitle="QUALITY_SCORE">
          <div className="space-y-6">
            <div className="p-4 bg-accent/5 border border-accent/10 rounded-sm text-center">
              <span className="text-[10px] uppercase font-bold text-accent tracking-widest block mb-2">Global Semantic Coverage</span>
              <div className="text-3xl font-bold text-ink-bright">94.2<span className="text-accent">%</span></div>
              <p className="text-[10px] text-ink/40 mt-1">Calculated across 4.5k entries</p>
            </div>

            <div className="space-y-3">
              <h5 className="text-[10px] font-bold text-ink/40 uppercase tracking-widest">Intent Distribution</h5>
              {intentDistribution.map((item, i) => (
                <div key={i} className="space-y-1">
                  <div className="flex justify-between text-[10px]">
                    <span>{item.label}</span>
                    <span className="font-bold">{item.val}%</span>
                  </div>
                  <div className="h-1 w-full bg-line rounded-full overflow-hidden">
                    <div className="h-full bg-accent" style={{ width: `${item.val}%` }} />
                  </div>
                </div>
              ))}
            </div>
          </div>
        </Card>

        <Card title="Recent Runs & Exports" subtitle="ARTIFACTS">
          <div className="space-y-4">
            <div>
              <div className="flex justify-between items-center mb-2">
                <span className="text-[10px] uppercase font-bold text-ink/40 tracking-widest">Runs</span>
                <span className="text-[10px] font-mono text-ink/50">{runs.length}</span>
              </div>
              <div className="space-y-2 max-h-40 overflow-y-auto custom-scrollbar pr-1">
                {runs.length > 0 ? runs.map((run) => (
                  <div key={run.id} className="p-2 bg-bg/70 border border-line/20 rounded-sm text-[10px]">
                    <div className="flex justify-between gap-2">
                      <span className="font-bold truncate">{run.npcKey}</span>
                      <span className="text-ink/40">{new Date(run.updatedAt).toLocaleDateString()}</span>
                    </div>
                    <div className="text-ink/60 text-[9px]">{run.id}</div>
                  </div>
                )) : <div className="text-[10px] text-ink/40">No active runs found.</div>}
              </div>
            </div>

            <div>
              <div className="flex justify-between items-center mb-2">
                <span className="text-[10px] uppercase font-bold text-ink/40 tracking-widest">Exports</span>
                <span className="text-[10px] font-mono text-ink/50">{exportArtifacts.length}</span>
              </div>
              <div className="space-y-2 max-h-40 overflow-y-auto custom-scrollbar pr-1">
                {exportArtifacts.length > 0 ? exportArtifacts.map((artifact) => (
                  <div key={`${artifact.npcKey}-${artifact.file}`} className="p-2 bg-bg/70 border border-line/20 rounded-sm text-[10px]">
                    <div className="flex justify-between gap-2">
                      <span className="font-bold truncate">{artifact.npcKey}</span>
                      <span className="text-ink/40">{new Date(artifact.updatedAt).toLocaleDateString()}</span>
                    </div>
                    <div className="text-ink/60 text-[9px] truncate">{artifact.file}</div>
                  </div>
                )) : <div className="text-[10px] text-ink/40">No export artifacts found.</div>}
              </div>
            </div>
          </div>
        </Card>
      </div>
    </motion.div>
  );
};
