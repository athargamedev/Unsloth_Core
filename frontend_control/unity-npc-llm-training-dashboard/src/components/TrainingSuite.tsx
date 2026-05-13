import { motion } from 'motion/react';
import { Shield } from 'lucide-react';
import { cn } from '../lib/utils';
import { Card } from './Card';
import type { Subject, TrainingConfig } from '../api';

interface TrainingSuiteProps {
  subjects: Subject[];
  trainingConfig: TrainingConfig;
  onUpdateTrainingConfig: (config: Partial<TrainingConfig>) => void;
  onLaunchTraining: () => Promise<void>;
}

export const TrainingSuite = ({
  subjects,
  trainingConfig,
  onUpdateTrainingConfig,
  onLaunchTraining,
}: TrainingSuiteProps) => (
  <motion.div
    key="training"
    initial={{ opacity: 0, y: 10 }}
    animate={{ opacity: 1, y: 0 }}
    exit={{ opacity: 0, y: -10 }}
    className="flex-1 overflow-hidden p-4 flex flex-col gap-6"
  >
    <div className="flex justify-between items-end">
      <h3 className="text-xs font-bold text-ink-bright uppercase tracking-widest">LoRA Hyperparameter Suite</h3>
      <div className="flex gap-2 text-[10px] font-mono text-ink/40">
        <span>LOADER: NF4_QUANT</span>
        <span className="text-success underline">READY_FOR_INIT</span>
      </div>
    </div>

    <div className="grid grid-cols-2 gap-4">
      <Card title="Structural Parameters" subtitle="RANK_AND_DIM">
        <div className="space-y-4">
          <div>
            <label className="text-[9px] uppercase font-bold text-ink/30 mb-1.5 block">Subject Spec</label>
            <select
              value={trainingConfig.spec}
              onChange={(e) => onUpdateTrainingConfig({ spec: e.target.value })}
              className="w-full bg-bg border border-line rounded px-3 py-2 text-xs font-mono focus:border-accent outline-none mb-2"
            >
              {subjects.map((subject) => (
                <option key={subject.id} value={subject.path}>{subject.path}</option>
              ))}
            </select>
            <label className="text-[9px] uppercase font-bold text-ink/30 mb-1.5 block">Preset</label>
            <input
              value={trainingConfig.preset}
              onChange={(e) => onUpdateTrainingConfig({ preset: e.target.value })}
              className="w-full bg-bg border border-line rounded px-3 py-2 text-xs font-mono focus:border-accent outline-none"
            />
          </div>
          <div>
            <label className="text-[9px] uppercase font-bold text-ink/30 mb-1.5 block">Base Model Path</label>
            <input
              value={trainingConfig.baseModel}
              onChange={(e) => onUpdateTrainingConfig({ baseModel: e.target.value })}
              className="w-full bg-bg border border-line rounded px-3 py-2 text-xs font-mono focus:border-accent outline-none"
            />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="text-[9px] uppercase font-bold text-ink/30 mb-1.5 block">LoRA Rank (R)</label>
              <input
                type="number"
                value={trainingConfig.rank}
                onChange={(e) => onUpdateTrainingConfig({ rank: parseInt(e.target.value) })}
                className="w-full bg-bg border border-line rounded px-3 py-2 text-xs font-mono focus:border-accent outline-none"
              />
              <p className="text-[8px] mt-1 text-ink/30">Higher = more capacity but larger file size.</p>
            </div>
            <div>
              <label className="text-[9px] uppercase font-bold text-ink/30 mb-1.5 block">LoRA Alpha</label>
              <input
                type="number"
                value={trainingConfig.alpha}
                onChange={(e) => onUpdateTrainingConfig({ alpha: parseInt(e.target.value) })}
                className="w-full bg-bg border border-line rounded px-3 py-2 text-xs font-mono focus:border-accent outline-none"
              />
            </div>
          </div>
        </div>
      </Card>

      <Card title="Optimization Logic" subtitle="SCHEDULER_V1">
        <div className="space-y-4">
          <div>
            <label className="text-[9px] uppercase font-bold text-ink/30 mb-1.5 block">Learning Rate</label>
            <div className="flex gap-2">
              <input
                value={trainingConfig.learningRate}
                onChange={(e) => onUpdateTrainingConfig({ learningRate: e.target.value })}
                className="flex-1 bg-bg border border-line rounded px-3 py-2 text-xs font-mono focus:border-accent outline-none"
              />
              <select className="bg-bg border border-line rounded px-2 text-[10px] text-ink/60 outline-none">
                <option>Cosine</option>
                <option>Linear</option>
                <option>Constant</option>
              </select>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="text-[9px] uppercase font-bold text-ink/30 mb-1.5 block">Batch Size</label>
              <select
                value={trainingConfig.batchSize}
                onChange={(e) => onUpdateTrainingConfig({ batchSize: parseInt(e.target.value) })}
                className="w-full bg-bg border border-line rounded px-3 py-2 text-xs font-mono focus:border-accent outline-none"
              >
                <option value={1}>1</option>
                <option value={2}>2</option>
                <option value={4}>4</option>
                <option value={8}>8</option>
                <option value={16}>16</option>
              </select>
            </div>
            <div>
              <label className="text-[9px] uppercase font-bold text-ink/30 mb-1.5 block">Epochs</label>
              <input
                type="number"
                value={trainingConfig.epochs}
                onChange={(e) => onUpdateTrainingConfig({ epochs: parseInt(e.target.value) })}
                className="w-full bg-bg border border-line rounded px-3 py-2 text-xs font-mono focus:border-accent outline-none"
              />
            </div>
          </div>
        </div>
      </Card>
    </div>

    <div className="mt-auto p-4 bg-accent/5 border border-accent/10 rounded-sm flex justify-between items-center">
      <div className="space-y-2">
        <div className="flex items-center gap-2">
          <Shield className="w-3 h-3 text-success" />
          <span className="text-[10px] font-bold text-success uppercase tracking-tighter">Config Validation Passed</span>
        </div>
        <p className="text-[10px] text-ink/40">Estimated VRAM requirement: 14.8GB (Optimized for 24GB+ cards)</p>
        <label className="flex items-center gap-2 cursor-pointer select-none">
          <input
            type="checkbox"
            checked={trainingConfig.wandb ?? false}
            onChange={(e) => onUpdateTrainingConfig({ wandb: e.target.checked })}
            className="w-3 h-3 accent-accent rounded"
          />
          <span className="text-[10px] font-bold text-accent uppercase tracking-tighter">Enable W&B Tracking</span>
        </label>
      </div>
      <button
        onClick={onLaunchTraining}
        className="px-6 py-2 bg-accent text-bg text-[11px] font-bold rounded-sm uppercase tracking-widest hover:brightness-110 active:scale-95 transition-all shadow-xl shadow-accent/20"
      >
        Launch Training Cluster
      </button>
    </div>
  </motion.div>
);
