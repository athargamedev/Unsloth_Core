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

const MODEL_PRESETS = [
  { value: '', label: 'None (manual model ID)' },
  { value: 'llama-3.2-3b', label: 'Llama 3.2 3B' },
  { value: 'qwen-2.5-1.7b', label: 'Qwen 2.5 1.7B' },
  { value: 'qwen-3-1.7b', label: 'Qwen3 1.7B' },
  { value: 'qwen-3-8b', label: 'Qwen3 8B' },
  { value: 'gemma-3-1b', label: 'Gemma 3 1B' },
  { value: 'gemma-3-12b', label: 'Gemma 3 12B' },
  { value: 'llama-3.1-8b', label: 'Llama 3.1 8B' },
];

const JUDGE_PRESETS = [
  { value: '', label: 'Default' },
  { value: 'strict', label: 'Strict' },
  { value: 'lenient', label: 'Lenient' },
  { value: 'balanced', label: 'Balanced' },
];

export const TrainingSuite = ({
  subjects,
  presets = [],
  presetDesc = {},
  trainingConfig,
  onUpdateTrainingConfig,
  onLaunchTraining,
}: TrainingSuiteProps) => {
  const modelId = trainingConfig.modelId || trainingConfig.baseModel;
  const vramGb = estimateVram(modelId, trainingConfig.rank);

  // Real config validation
  const validation = (() => {
    const issues: string[] = [];
    if (!trainingConfig.spec) issues.push('No subject spec selected');
    if (!modelId) issues.push('Model ID is empty');
    if (trainingConfig.rank < 1 || trainingConfig.rank > 256) issues.push('LoRA rank should be 1–256');
    if (trainingConfig.alpha < 1 || trainingConfig.alpha > 512) issues.push('LoRA alpha should be 1–512');
    if (trainingConfig.epochs < 1) issues.push('Epochs must be at least 1');
    const lr = parseFloat(trainingConfig.learningRate);
    if (isNaN(lr) || lr <= 0) issues.push('Learning rate must be a positive number');

    const valid = issues.length === 0;
    const hint = valid
      ? `Estimated VRAM: ~${vramGb}GB (${modelId.split('/').pop() || 'model'}, rank=${trainingConfig.rank})`
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

            {/* Model Selection */}
            <div>
              <label className="text-[12px] uppercase font-bold text-ink/30 mb-1.5 block">Model ID</label>
              <input
                value={trainingConfig.modelId}
                onChange={(e) => onUpdateTrainingConfig({ modelId: e.target.value })}
                placeholder="e.g., unsloth/Qwen3-1.7B-bnb-4bit"
                className="w-full bg-bg border border-line rounded px-3 py-2 text-xs font-mono focus:border-accent outline-none"
              />
            </div>
            <div>
              <label className="text-[12px] uppercase font-bold text-ink/30 mb-1.5 block">Model Preset</label>
              <select
                value={trainingConfig.modelPreset}
                onChange={(e) => onUpdateTrainingConfig({ modelPreset: e.target.value })}
                className="w-full bg-bg border border-line rounded px-3 py-2 text-xs font-mono focus:border-accent outline-none"
              >
                {MODEL_PRESETS.map((mp) => (
                  <option key={mp.value} value={mp.value}>{mp.label}</option>
                ))}
              </select>
              <p className="text-[8px] mt-1 text-ink/30">Mutually exclusive with Model ID — preset overrides ID if set</p>
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

        <div className="space-y-4">
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

          {/* Export Options */}
          <Card title="Export Options" subtitle="GGUF_V1">
            <div className="space-y-3">
              <label className="flex items-center gap-2 cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={trainingConfig.exportGguf ?? true}
                  onChange={(e) => onUpdateTrainingConfig({ exportGguf: e.target.checked })}
                  className="w-3 h-3 accent-accent rounded"
                />
                <span className="text-[10px] font-bold uppercase tracking-tighter">Export GGUF After Training</span>
              </label>
              {trainingConfig.exportGguf && (
                <label className="flex items-center gap-2 cursor-pointer select-none ml-4">
                  <input
                    type="checkbox"
                    checked={trainingConfig.fullMergeExport ?? false}
                    onChange={(e) => onUpdateTrainingConfig({ fullMergeExport: e.target.checked })}
                    className="w-3 h-3 accent-accent rounded"
                  />
                  <span className="text-[10px] text-ink/70 uppercase tracking-tighter">Full Merge Export</span>
                </label>
              )}
            </div>
          </Card>
        </div>
      </div>

      {/* Quality Gate Section */}
      <div className="border border-line/30 rounded-sm p-4 bg-surface/20">
        <h4 className="text-[11px] font-bold text-ink/60 uppercase tracking-wider mb-3 flex items-center gap-2">
          <Shield className="w-3 h-3" />
          Dataset Quality Gate (DeepEval)
        </h4>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-[11px]">
          <div>
            <label className="flex items-center gap-2 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={trainingConfig.datasetEvalSkip ?? false}
                onChange={(e) => onUpdateTrainingConfig({ datasetEvalSkip: e.target.checked })}
                className="w-3 h-3 accent-accent rounded"
              />
              <span className="text-[10px] uppercase tracking-tighter">Skip Quality Gate</span>
            </label>
          </div>
          <div>
            <label className="block text-[10px] font-bold text-ink/40 uppercase mb-1">Judge Model</label>
            <input
              type="text"
              value={trainingConfig.datasetEvalJudgeModel || ''}
              onChange={(e) => onUpdateTrainingConfig({ datasetEvalJudgeModel: e.target.value })}
              placeholder="qwen3:latest"
              className="w-full bg-bg border border-line rounded px-2 py-1.5 text-[11px] font-mono"
            />
          </div>
          <div>
            <label className="block text-[10px] font-bold text-ink/40 uppercase mb-1">Judge Preset</label>
            <select
              value={trainingConfig.datasetEvalJudgePreset || ''}
              onChange={(e) => onUpdateTrainingConfig({ datasetEvalJudgePreset: e.target.value })}
              className="w-full bg-bg border border-line rounded px-2 py-1.5 text-[11px]"
            >
              {JUDGE_PRESETS.map((jp) => (
                <option key={jp.value} value={jp.value}>{jp.label}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="flex items-center gap-2 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={trainingConfig.deepevalSoftFail ?? false}
                onChange={(e) => onUpdateTrainingConfig({ deepevalSoftFail: e.target.checked })}
                className="w-3 h-3 accent-accent rounded"
              />
              <span className="text-[10px] uppercase tracking-tighter">Soft Fail</span>
            </label>
          </div>
          <div>
            <label className="block text-[10px] font-bold text-ink/40 uppercase mb-1">Ollama URL</label>
            <input
              type="text"
              value={trainingConfig.deepevalOllamaUrl || ''}
              onChange={(e) => onUpdateTrainingConfig({ deepevalOllamaUrl: e.target.value })}
              placeholder="http://localhost:11434"
              className="w-full bg-bg border border-line rounded px-2 py-1.5 text-[11px] font-mono"
            />
          </div>
          <div>
            <label className="block text-[10px] font-bold text-ink/40 uppercase mb-1">Cases per Category</label>
            <input
              type="number"
              value={trainingConfig.deepevalCasesPerCategory ?? 5}
              onChange={(e) => onUpdateTrainingConfig({ deepevalCasesPerCategory: parseInt(e.target.value) || 5 })}
              min={1} max={20}
              className="w-20 bg-bg border border-line rounded px-2 py-1.5 text-[11px]"
            />
          </div>
        </div>
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
