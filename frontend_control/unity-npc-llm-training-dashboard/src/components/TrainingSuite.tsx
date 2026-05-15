import { motion } from 'motion/react';
import { Shield } from 'lucide-react';
import { cn } from '../lib/utils';
import { Card } from './Card';
import type { Subject, TrainingConfig } from '../api';

interface TrainingSuiteProps {
  subjects: Subject[];
  presets?: Array<{ name: string; description: string }>;
  presetDesc?: Record<string, string>;
  trainingConfig: TrainingConfig;
  onUpdateTrainingConfig: (config: Partial<TrainingConfig>) => void;
  onLaunchTraining: () => Promise<void>;
}

/** Replicates train.py's estimate_vram() logic for the frontend */
function estimateVram(modelName: string, rank: number, packing = true, maxSeq = 2048): number {
  const name = modelName.toLowerCase();
  let gb = 8.0; // baseline for 1.7B–3B
  if (name.includes('8b')) gb = 14.0;
  else if (name.includes('7b')) gb = 12.0;
  else if (name.includes('3b')) gb = 8.0;
  else if (name.includes('1b')) gb = 4.0;

  gb += (rank - 16) * 0.1;
  gb *= maxSeq / 2048;
  if (packing) gb *= 0.85;

  return Math.round(gb * 10) / 10;
}

export const TrainingSuite = ({
  subjects,
  presets = [],
  presetDesc = {},
  trainingConfig,
  onUpdateTrainingConfig,
  onLaunchTraining,
}: TrainingSuiteProps) => {
  const vramGb = estimateVram(trainingConfig.baseModel, trainingConfig.rank);

  // Real config validation
  const validation = (() => {
    const issues: string[] = [];
    if (!trainingConfig.spec) issues.push('No subject spec selected');
    if (!trainingConfig.baseModel) issues.push('Base model path is empty');
    if (trainingConfig.rank < 1 || trainingConfig.rank > 256) issues.push('LoRA rank should be 1–256');
    if (trainingConfig.alpha < 1 || trainingConfig.alpha > 512) issues.push('LoRA alpha should be 1–512');
    if (trainingConfig.epochs < 1) issues.push('Epochs must be at least 1');
    const lr = parseFloat(trainingConfig.learningRate);
    if (isNaN(lr) || lr <= 0) issues.push('Learning rate must be a positive number');

    const valid = issues.length === 0;
    const hint = valid
      ? `Estimated VRAM: ~${vramGb}GB (${trainingConfig.baseModel.split('/').pop() || 'model'}, rank=${trainingConfig.rank})`
      : '';

    return { valid, issues, hint };
  })();

  return (
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
          <span className={cn(
            'underline',
            validation.valid ? 'text-success' : 'text-warning',
          )}>{validation.valid ? 'READY_FOR_INIT' : 'CHECK_CONFIG'}</span>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <Card title="Structural Parameters" subtitle="RANK_AND_DIM">
          <div className="space-y-4">
            <div>
              <label className="text-[12px] uppercase font-bold text-ink/30 mb-1.5 block">Subject Spec</label>
              <select
                value={trainingConfig.spec}
                onChange={(e) => onUpdateTrainingConfig({ spec: e.target.value })}
                className="w-full bg-bg border border-line rounded px-3 py-2 text-xs font-mono focus:border-accent outline-none mb-2"
              >
                {subjects.map((subject) => (
                  <option key={subject.id} value={subject.path}>{subject.path}</option>
                ))}
              </select>

              <label className="text-[12px] uppercase font-bold text-ink/30 mb-1.5 block">Preset</label>
              <select
                value={trainingConfig.preset}
                onChange={(e) => onUpdateTrainingConfig({ preset: e.target.value })}
                className="w-full bg-bg border border-line rounded px-3 py-2 text-xs font-mono focus:border-accent outline-none"
              >
                <option value="">None (manual config)</option>
                {presets.map((p) => (
                  <option key={p.name} value={p.name}>{p.name}</option>
                ))}
              </select>
              {trainingConfig.preset && presetDesc[trainingConfig.preset] && (
                <p className="text-[8px] mt-1 text-ink/30 italic">{presetDesc[trainingConfig.preset]}</p>
              )}

              <label className="text-[12px] uppercase font-bold text-ink/30 mb-1.5 block mt-4">Dataset Technique</label>
              <select
                value={trainingConfig.technique}
                onChange={(e) => onUpdateTrainingConfig({ technique: e.target.value })}
                className="w-full bg-bg border border-line rounded px-3 py-2 text-xs font-mono focus:border-accent outline-none"
              >
                <option value="docs">docs</option>
                <option value="template">template</option>
                <option value="onyx">onyx</option>
                <option value="ollama">ollama</option>
                <option value="openai">openai</option>
                <option value="anthropic">anthropic</option>
              </select>
            </div>
            <div>
              <label className="text-[12px] uppercase font-bold text-ink/30 mb-1.5 block">Base Model Path</label>
              <input
                value={trainingConfig.baseModel}
                onChange={(e) => onUpdateTrainingConfig({ baseModel: e.target.value })}
                className="w-full bg-bg border border-line rounded px-3 py-2 text-xs font-mono focus:border-accent outline-none"
              />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="text-[12px] uppercase font-bold text-ink/30 mb-1.5 block">LoRA Rank (R)</label>
                <input
                  type="number"
                  value={trainingConfig.rank}
                  onChange={(e) => onUpdateTrainingConfig({ rank: parseInt(e.target.value) || 0 })}
                  className="w-full bg-bg border border-line rounded px-3 py-2 text-xs font-mono focus:border-accent outline-none"
                />
                <p className="text-[8px] mt-1 text-ink/30">Higher = more capacity but larger file size.</p>
              </div>
              <div>
                <label className="text-[12px] uppercase font-bold text-ink/30 mb-1.5 block">LoRA Alpha</label>
                <input
                  type="number"
                  value={trainingConfig.alpha}
                  onChange={(e) => onUpdateTrainingConfig({ alpha: parseInt(e.target.value) || 0 })}
                  className="w-full bg-bg border border-line rounded px-3 py-2 text-xs font-mono focus:border-accent outline-none"
                />
              </div>
            </div>
          </div>
        </Card>

        <Card title="Optimization Logic" subtitle="SCHEDULER_V1">
          <div className="space-y-4">
            <div>
              <label className="text-[12px] uppercase font-bold text-ink/30 mb-1.5 block">Learning Rate</label>
              <div className="flex gap-2">
                <input
                  value={trainingConfig.learningRate}
                  onChange={(e) => onUpdateTrainingConfig({ learningRate: e.target.value })}
                  className="flex-1 bg-bg border border-line rounded px-3 py-2 text-xs font-mono focus:border-accent outline-none"
                />
                <select
                  value={trainingConfig.scheduler}
                  onChange={(e) => onUpdateTrainingConfig({ scheduler: e.target.value as any })}
                  className="bg-bg border border-line rounded px-2 text-[10px] text-ink/60 outline-none"
                >
                  <option value="cosine">Cosine</option>
                  <option value="linear">Linear</option>
                  <option value="constant">Constant</option>
                </select>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="text-[12px] uppercase font-bold text-ink/30 mb-1.5 block">Batch Size</label>
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
                <label className="text-[12px] uppercase font-bold text-ink/30 mb-1.5 block">Epochs</label>
                <input
                  type="number"
                  value={trainingConfig.epochs}
                  onChange={(e) => onUpdateTrainingConfig({ epochs: parseInt(e.target.value) || 0 })}
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
            <Shield className={`w-3 h-3 ${validation.valid ? 'text-success' : 'text-warning'}`} />
            <span className={`text-[10px] font-bold uppercase tracking-tighter ${validation.valid ? 'text-success' : 'text-warning'}`}>
              {validation.valid ? 'Config Validation Passed' : validation.issues[0]}
            </span>
          </div>
          {validation.valid && (
            <p className="text-[10px] text-ink/40">{validation.hint}</p>
          )}
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
          disabled={!validation.valid}
          className={`px-6 py-2 text-[11px] font-bold rounded-sm uppercase tracking-widest transition-all active:scale-95 ${
            validation.valid
              ? 'bg-accent text-bg hover:brightness-110 shadow-xl shadow-accent/20'
              : 'bg-line/30 text-ink/30 cursor-not-allowed'
          }`}
        >
          Launch Training Cluster
        </button>
      </div>
    </motion.div>
  );
};
