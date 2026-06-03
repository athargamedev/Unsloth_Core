import { motion } from 'motion/react';
import { Shield } from 'lucide-react';
import { useCallback, useMemo } from 'react';
import { cn } from '../lib/utils';
import { Card } from './Card';
import { DynamicCommandForm } from './DynamicCommandForm';
import type { Subject, TrainingConfig } from '../api';
import type { CommandFieldSchema } from '../schemas/command-field';

const CARD_FIELD_GROUPS = {
  structural: ['spec', 'preset', 'options.technique', 'options.modelId', 'options.rank', 'options.alpha'],
  optimization: ['options.learningRate', 'options.scheduler', 'options.batchSize', 'options.epochs'],
  export: ['options.exportGguf', 'options.fullMergeExport'],
} as const;

interface TrainingSuiteProps {
  subjects: Subject[];
  presets?: Array<{ name: string; description: string }>;
  presetDesc?: Record<string, string>;
  trainingConfig: TrainingConfig;
  onUpdateTrainingConfig: (config: Partial<TrainingConfig>) => void;
  onLaunchTraining: () => Promise<void>;
  trainSchema?: Record<string, CommandFieldSchema>;
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

const hfPresets = [
  'unsloth/Llama-3.2-1B-Instruct-bnb-4bit',
  'unsloth/Llama-3.2-3B-Instruct-bnb-4bit',
  'unsloth/Meta-Llama-3.1-8B-Instruct-bnb-4bit',
];

export const TrainingSuite = ({
  subjects,
  presets = [],
  presetDesc = {},
  trainingConfig,
  onUpdateTrainingConfig,
  onLaunchTraining,
  trainSchema,
}: TrainingSuiteProps) => {
  const modelId = trainingConfig.modelId || trainingConfig.baseModel;
  const vramGb = estimateVram(modelId, trainingConfig.rank);

  // Build schema-flat values object mapping dotted fieldPaths -> TrainingConfig fields
  const schemaValues = useMemo(() => {
    const map: Record<string, unknown> = {};
    map['spec'] = trainingConfig.spec;
    map['preset'] = trainingConfig.preset;
    if (trainingConfig.technique) map['options.technique'] = trainingConfig.technique;
    if (trainingConfig.modelId) map['options.modelId'] = trainingConfig.modelId;
    if (trainingConfig.wandb !== undefined) map['options.wandb'] = trainingConfig.wandb;
    if (trainingConfig.learningRate) map['options.learningRate'] = trainingConfig.learningRate;
    if (trainingConfig.batchSize) map['options.batchSize'] = trainingConfig.batchSize;
    if (trainingConfig.epochs) map['options.epochs'] = trainingConfig.epochs;
    if (trainingConfig.rank) map['options.rank'] = trainingConfig.rank;
    if (trainingConfig.alpha) map['options.alpha'] = trainingConfig.alpha;
    if (trainingConfig.scheduler) map['options.scheduler'] = trainingConfig.scheduler;
    if (trainingConfig.exportGguf !== undefined) map['options.exportGguf'] = trainingConfig.exportGguf;
    if (trainingConfig.fullMergeExport !== undefined) map['options.fullMergeExport'] = trainingConfig.fullMergeExport;
    if (trainingConfig.datasetEvalSkip !== undefined) map['options.datasetEvalSkip'] = trainingConfig.datasetEvalSkip;
    return map;
  }, [trainingConfig]);

  // Map dotted fieldPaths back to flat TrainingConfig keys
  const handleFieldChange = useCallback((fieldPath: string, value: unknown) => {
    const configKey = fieldPath.startsWith('options.')
      ? fieldPath.slice('options.'.length)
      : fieldPath;
    onUpdateTrainingConfig({ [configKey]: value } as Partial<TrainingConfig>);
  }, [onUpdateTrainingConfig]);

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

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Card title="Structural Parameters" subtitle="RANK_AND_DIM">
          {trainSchema ? (
            <DynamicCommandForm
              commandId="train"
              fields={trainSchema}
              values={schemaValues}
              onChange={handleFieldChange}
              fieldKeys={CARD_FIELD_GROUPS.structural}
              hideCommandId
            />
          ) : (
            <div className="text-xs text-ink/40 italic py-4 text-center">Loading schema...</div>
          )}
        </Card>

        <div className="space-y-4">
          <Card title="Optimization Logic" subtitle="SCHEDULER_V1">
            {trainSchema ? (
              <DynamicCommandForm
                commandId="train"
                fields={trainSchema}
                values={schemaValues}
                onChange={handleFieldChange}
                fieldKeys={CARD_FIELD_GROUPS.optimization}
                hideCommandId
              />
            ) : (
              <div className="text-xs text-ink/40 italic py-4 text-center">Loading schema...</div>
            )}
          </Card>

          {/* Export Options */}
          <Card title="Export Options" subtitle="GGUF_V1">
            {trainSchema ? (
              <DynamicCommandForm
                commandId="train"
                fields={trainSchema}
                values={schemaValues}
                onChange={handleFieldChange}
                fieldKeys={CARD_FIELD_GROUPS.export}
                hideCommandId
              />
            ) : (
              <div className="text-xs text-ink/40 italic py-4 text-center">Loading schema...</div>
            )}
          </Card>
        </div>
      </div>

      {/* Quality Gate Section */}
      <div className="border border-line/30 rounded-sm p-4 bg-surface/20">
        <h4 className="text-[11px] font-bold text-ink/60 uppercase tracking-wider mb-3 flex items-center gap-2">
          <Shield className="w-3 h-3" />
          Dataset Quality Gate
        </h4>
        <div className="space-y-2 text-[11px]">
          <p className="text-ink/50">
            Training expects a fresh passing <code>ucore dataset-eval</code> artifact for the selected sanitized dataset. Configure judge model, preset, and sampling in the dataset pipeline before launching training.
          </p>
          <label className="flex items-center gap-2 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={trainingConfig.datasetEvalSkip ?? false}
              onChange={(e) => onUpdateTrainingConfig({ datasetEvalSkip: e.target.checked })}
              className="w-3 h-3 accent-warning rounded"
            />
            <span className="text-[10px] uppercase tracking-tighter text-warning">Allow ungated training (--allow-ungated-dataset)</span>
          </label>
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
