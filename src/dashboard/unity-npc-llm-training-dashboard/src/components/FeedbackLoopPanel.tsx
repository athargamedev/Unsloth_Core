import { useState, useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { z } from 'zod';
import { fetchOptionalJson } from '../api';
import type { FeedbackFileInfo } from '../api';
import { useFeedbackResultsQuery } from '../hooks/useReactQuery';
import { useOllamaModels } from '../hooks/useOllamaModels';
import { RefreshCw } from 'lucide-react';

// 1. Zod Schema Definition
const FeedbackGapResultSchema = z.object({
  concept: z.string(),
  category: z.string(),
  gap_type: z.enum(['training_density', 'knowledge_gap']),
  onyx_result_count: z.number(),
  onyx_sources: z.array(z.string()).optional(),
});

const ConceptFeedbackSchema = z.object({
  total: z.number(),
  baseline_wins: z.number(),
  candidate_wins: z.number(),
  ties: z.number(),
  win_rate: z.number(),
  avg_baseline_quality: z.number(),
  avg_candidate_quality: z.number(),
  constraint_violations: z.number(),
  examples: z.array(z.record(z.string(), z.unknown())).optional(),
});

const FeedbackResultSchema = z.object({
  npc_key: z.string(),
  baseline: z.string(),
  candidate: z.string(),
  total_examples: z.number(),
  baseline_wins: z.number(),
  candidate_wins: z.number(),
  ties: z.number(),
  win_rate: z.number(),
  per_concept: z.record(z.string(), ConceptFeedbackSchema),
  weak_concepts: z.array(z.string()),
  timestamp: z.string(),
  gaps: z.array(FeedbackGapResultSchema).optional(),
});

type ValidatedFeedbackResult = z.infer<typeof FeedbackResultSchema>;
type FeedbackGapResult = z.infer<typeof FeedbackGapResultSchema>;
type ConceptFeedback = z.infer<typeof ConceptFeedbackSchema>;

interface FeedbackConfig {
  // Execution modes
  dryRun: boolean;
  skipGapDetection: boolean;
  autoRetrain: boolean;
  auto: boolean;
  // Thresholds
  winRateThreshold: number;
  qualityThreshold: number;
  violationThreshold: number;
  // Training
  trainPreset: string;
  // Alternative mode
  spec: string;
  candidate: string;
  // Regeneration
  regenerationTechnique: string;
  regenerationPreset: string;
  regenerationModel: string;
  regenerationUrl: string;
  regenerationBatchSize: number;
  // DeepEval
  deepevalJudgePreset: string;
  deepevalJudgeModel: string;
  deepevalOllamaUrl: string;
  deepevalCasesPerCategory: number;
  deepevalSoftFail: boolean;
  skipDatasetEval: boolean;
  // Output
  saveGaps: boolean;
  json: boolean;
}

const JUDGE_PRESETS = [
  { value: '', label: 'Default' },
  { value: 'strict', label: 'Strict' },
  { value: 'lenient', label: 'Lenient' },
  { value: 'balanced', label: 'Balanced' },
];

const REGEN_TECHNIQUES = [
  { value: 'template', label: 'Template' },
  { value: 'docs', label: 'Docs' },
  { value: 'ollama', label: 'Ollama' },
  { value: 'openai', label: 'OpenAI' },
  { value: 'anthropic', label: 'Anthropic' },
];

const TRAIN_PRESETS = [
  { value: 'smoke', label: 'Smoke' },
  { value: 'fast-3b', label: 'Fast 3B' },
  { value: 'safe-any', label: 'Safe Any' },
  { value: 'quality', label: 'Quality' },
  { value: 'premium-3b', label: 'Premium 3B' },
  { value: 'premium-8b', label: 'Premium 8B' },
];

export const FeedbackLoopPanel = () => {
  const ollamaModels = useOllamaModels();
  const [selectedFile, setSelectedFile] = useState<FeedbackFileInfo | null>(null);
  const [apiError, setApiError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [showConfig, setShowConfig] = useState(false);
  const [fbConfig, setFbConfig] = useState<FeedbackConfig>({
    dryRun: true,
    skipGapDetection: false,
    autoRetrain: false,
    auto: false,
    winRateThreshold: 0.5,
    qualityThreshold: 25.0,
    violationThreshold: 1,
    trainPreset: 'fast-3b',
    spec: '',
    candidate: '',
    regenerationTechnique: 'template',
    regenerationPreset: '',
    regenerationModel: '',
    regenerationUrl: '',
    regenerationBatchSize: 4,
    deepevalJudgePreset: '',
    deepevalJudgeModel: '',
    deepevalOllamaUrl: '',
    deepevalCasesPerCategory: 1,
    deepevalSoftFail: false,
    skipDatasetEval: false,
    saveGaps: false,
    json: false,
  });

  const { data: feedbackFiles = [], isLoading: loading, refetch: loadFiles } = useFeedbackResultsQuery();

  // Auto-select most recent file
  useEffect(() => {
    if (feedbackFiles.length > 0 && !selectedFile) {
      setSelectedFile(feedbackFiles[0]);
    }
  }, [feedbackFiles, selectedFile]);

  // 2. React Query Usage for Feedback Details
  const { data: feedbackData, isLoading: detailLoading, error: detailError } = useQuery<ValidatedFeedbackResult | null, unknown>({
    queryKey: ['feedback-result-detail', selectedFile?.path],
    queryFn: async () => {
      if (!selectedFile) return null;
      const rawData = await fetchOptionalJson<unknown>(`/api/feedback-result/file?path=${encodeURIComponent(selectedFile.path)}`);
      if (!rawData) return null;
      return FeedbackResultSchema.parse(rawData);
    },
    enabled: !!selectedFile,
  });

  const updateConfig = <K extends keyof FeedbackConfig>(key: K, value: FeedbackConfig[K]) => {
    setFbConfig(prev => ({ ...prev, [key]: value }));
  };

  const handleRunFeedback = async () => {
    // Validate: either a feedback file or spec+candidate must be provided
    if (!selectedFile && !fbConfig.spec.trim() && !fbConfig.candidate.trim()) {
      setApiError('Select a feedback result OR provide spec + candidate for alternative mode');
      return;
    }
    setRunning(true);
    setApiError(null);
    try {
      const payload: Record<string, unknown> = {
        commandId: 'feedback',
        type: 'Feedback',
        options: {},
      };

      // Primary mode: feedback_json
      if (selectedFile) {
        payload.feedback_json = `eval/results/feedback/${selectedFile.name}`;
      }

      // Alternative mode: spec + candidate
      if (fbConfig.spec.trim()) {
        payload.spec = fbConfig.spec.trim();
        (payload.options as Record<string, unknown>).spec = fbConfig.spec.trim();
      }
      if (fbConfig.candidate.trim()) {
        (payload.options as Record<string, unknown>).candidate = fbConfig.candidate.trim();
      }

      // Execution modes
      if (fbConfig.dryRun) payload['dry-run'] = true;
      if (fbConfig.auto) {
        payload['auto'] = true;
        (payload.options as Record<string, unknown>).auto = true;
      }
      if (fbConfig.skipGapDetection) payload['skip-gap-detection'] = true;
      if (fbConfig.autoRetrain) {
        payload['auto-retrain'] = true;
        payload['train-preset'] = fbConfig.trainPreset;
        (payload.options as Record<string, unknown>).trainPreset = fbConfig.trainPreset;
      }

      // Thresholds
      if (fbConfig.winRateThreshold !== 0.5) {
        (payload.options as Record<string, unknown>).winRateThreshold = String(fbConfig.winRateThreshold);
      }
      if (fbConfig.qualityThreshold !== 25.0) {
        (payload.options as Record<string, unknown>).qualityThreshold = String(fbConfig.qualityThreshold);
      }
      if (fbConfig.violationThreshold !== 1) {
        (payload.options as Record<string, unknown>).violationThreshold = String(fbConfig.violationThreshold);
      }

      // Regeneration
      if (fbConfig.regenerationTechnique && fbConfig.regenerationTechnique !== 'template') {
        (payload.options as Record<string, unknown>).regenerationTechnique = fbConfig.regenerationTechnique;
      }
      if (fbConfig.regenerationPreset) {
        (payload.options as Record<string, unknown>).regenerationPreset = fbConfig.regenerationPreset;
      }
      if (fbConfig.regenerationModel) {
        (payload.options as Record<string, unknown>).regenerationModel = fbConfig.regenerationModel;
      }
      if (fbConfig.regenerationUrl) {
        (payload.options as Record<string, unknown>).regenerationUrl = fbConfig.regenerationUrl;
      }
      if (fbConfig.regenerationBatchSize !== 4) {
        (payload.options as Record<string, unknown>).regenerationBatchSize = String(fbConfig.regenerationBatchSize);
      }

      // DeepEval
      if (fbConfig.deepevalJudgePreset) {
        (payload.options as Record<string, unknown>).deepevalJudgePreset = fbConfig.deepevalJudgePreset;
      }
      if (fbConfig.deepevalJudgeModel) {
        (payload.options as Record<string, unknown>).deepevalJudgeModel = fbConfig.deepevalJudgeModel;
      }
      if (fbConfig.deepevalOllamaUrl) {
        (payload.options as Record<string, unknown>).deepevalOllamaUrl = fbConfig.deepevalOllamaUrl;
      }
      if (fbConfig.deepevalCasesPerCategory !== 1) {
        (payload.options as Record<string, unknown>).deepevalCasesPerCategory = String(fbConfig.deepevalCasesPerCategory);
      }
      if (fbConfig.deepevalSoftFail) {
        (payload.options as Record<string, unknown>).deepevalSoftFail = true;
      }
      if (fbConfig.skipDatasetEval) {
        payload['skip-dataset-eval'] = true;
        (payload.options as Record<string, unknown>).skipDatasetEval = true;
      }

      // Output
      if (fbConfig.saveGaps) payload['save-gaps'] = true;
      if (fbConfig.json) payload['json'] = true;

      const response = await fetch('/api/commands/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!response.ok) {
        const err = await response.json().catch(() => ({}));
        throw new Error(err.error || 'Failed to start feedback loop');
      }
    } catch (err) {
      setApiError(err instanceof Error ? err.message : 'Feedback loop failed');
    } finally {
      setRunning(false);
    }
  };

  const gapColor = (gap: FeedbackGapResult) => {
    return gap.gap_type === 'training_density' ? 'text-warning' : 'text-danger';
  };
  const gapBg = (gap: FeedbackGapResult) => {
    return gap.gap_type === 'training_density' ? 'bg-warning/10 border-warning/30' : 'bg-danger/10 border-danger/30';
  };

  const conceptWinRateColor = (wr: number) => {
    if (wr >= 0.5) return 'text-success';
    if (wr >= 0.25) return 'text-warning';
    return 'text-danger';
  };

  return (
    <div className="flex-1 flex flex-col overflow-hidden min-h-0 min-w-0">
      {/* Header */}
      <div className="p-4 border-b border-line bg-surface/30 flex items-center justify-between">
        <div>
          <h3 className="text-xs font-bold text-ink-bright uppercase tracking-widest">Feedback Loop</h3>
          <p className="text-[10px] text-ink/40">Analyze evaluation results and trigger self-improvement</p>
        </div>
        <button
          onClick={() => loadFiles()}
          className="px-2 py-1 bg-line/20 text-ink/60 text-[10px] rounded hover:bg-line/40 transition-colors"
        >
          Refresh
        </button>
      </div>

      {(apiError || detailError) && (
        <div className="mx-4 mt-2 p-2 bg-danger/10 border border-danger/30 rounded text-[11px] text-danger">
          {apiError || (detailError instanceof Error ? detailError.message : String(detailError))}
        </div>
      )}

      <div className="flex flex-col lg:flex-row flex-1 overflow-hidden min-h-0 min-w-0">
        {/* Left sidebar: file list */}
        <div className="w-full lg:w-56 border-r-0 lg:border-r border-b lg:border-b-0 border-line overflow-y-auto p-2 space-y-1 custom-scrollbar bg-surface/20 min-h-0 min-w-0">
          <div className="text-[10px] font-bold text-ink/40 uppercase tracking-widest px-2 py-1">Results</div>
          {loading && <div className="text-[10px] text-ink/30 px-2 py-4 text-center">Loading…</div>}
          {!loading && feedbackFiles.length === 0 && (
            <div className="text-[10px] text-ink/30 px-2 py-4 text-center">
              No feedback results.<br />
              <span className="text-accent">Run evaluation with --feedback-json first.</span>
            </div>
          )}
          {feedbackFiles.map((file) => (
            <button
              key={file.path}
              onClick={() => setSelectedFile(file)}
              className={`w-full text-left px-2 py-1.5 text-[10px] font-mono rounded transition-colors ${
                selectedFile?.path === file.path
                  ? 'bg-accent/20 text-accent border border-accent/30'
                  : 'hover:bg-line/20 text-ink/70'
              }`}
            >
              <div className="truncate">{file.name}</div>
              <div className="text-[8px] text-ink/30">
                {new Date(file.lastModified).toLocaleDateString()} {new Date(file.lastModified).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
              </div>
            </button>
          ))}
        </div>

        {/* Main content */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4 custom-scrollbar min-w-0 min-h-0">
          {detailLoading && (
            <div className="text-[12px] text-ink/40 text-center py-8">Loading feedback data…</div>
          )}

          {!detailLoading && !feedbackData && (
            <div className="h-full flex items-center justify-center text-ink/30">
              <div className="text-center space-y-2">
                <div className="text-[12px] font-bold uppercase tracking-widest">No Data</div>
                <div className="text-[10px]">Select a feedback result from the sidebar</div>
              </div>
            </div>
          )}

          {feedbackData && (
            <>
              {/* Summary cards */}
              <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3">
                <div className="bg-surface border border-line rounded-sm p-3">
                  <div className="text-[10px] font-bold text-ink/40 uppercase">NPC</div>
                  <div className="text-sm font-bold text-ink-bright font-mono">{feedbackData.npc_key}</div>
                </div>
                <div className="bg-surface border border-line rounded-sm p-3">
                  <div className="text-[10px] font-bold text-ink/40 uppercase">Overall Win Rate</div>
                  <div className={`text-lg font-bold font-mono ${conceptWinRateColor(feedbackData.win_rate)}`}>
                    {(feedbackData.win_rate * 100).toFixed(0)}%
                  </div>
                </div>
                <div className="bg-surface border border-line rounded-sm p-3">
                  <div className="text-[10px] font-bold text-ink/40 uppercase">Ties</div>
                  <div className="text-lg font-bold text-ink-bright">{feedbackData.ties}</div>
                </div>
                <div className="bg-surface border border-line rounded-sm p-3">
                  <div className="text-[10px] font-bold text-ink/40 uppercase">Questions</div>
                  <div className="text-lg font-bold text-ink-bright">{feedbackData.total_examples}</div>
                </div>
              </div>

              {/* Baseline / Candidate labels */}
              <div className="flex flex-col gap-1 sm:flex-row sm:flex-wrap sm:gap-4 text-[10px] text-ink/50 font-mono">
                <span>Baseline: <span className="text-ink/80">{feedbackData.baseline}</span></span>
                <span>Candidate: <span className="text-ink/80">{feedbackData.candidate}</span></span>
                <span>Date: <span className="text-ink/80">{feedbackData.timestamp}</span></span>
              </div>

              {/* Per-concept breakdown */}
              <div>
                <h4 className="text-[11px] font-bold text-ink-bright mb-2 uppercase tracking-wider">Per-Concept Breakdown</h4>
                <div className="overflow-x-auto">
                  <table className="w-full text-[10px] border-collapse">
                    <thead>
                      <tr className="bg-line/20">
                        <th className="text-left px-3 py-1.5 font-bold text-ink/60">Concept</th>
                        <th className="text-right px-3 py-1.5 font-bold text-ink/60">Win Rate</th>
                        <th className="text-right px-3 py-1.5 font-bold text-ink/60">Quality</th>
                        <th className="text-right px-3 py-1.5 font-bold text-ink/60">Violations</th>
                        <th className="text-right px-3 py-1.5 font-bold text-ink/60">Count</th>
                      </tr>
                    </thead>
                    <tbody>
                      {Object.entries(feedbackData.per_concept).map(([concept, info]: [string, ConceptFeedback]) => (
                        <tr key={concept} className="border-b border-line/20 hover:bg-line/10">
                          <td className="px-3 py-1.5 font-mono text-ink-bright">{concept}</td>
                          <td className={`px-3 py-1.5 text-right font-mono font-bold ${conceptWinRateColor(info.win_rate)}`}>
                            {(info.win_rate * 100).toFixed(0)}%
                          </td>
                          <td className="px-3 py-1.5 text-right font-mono text-ink/70">{info.avg_candidate_quality.toFixed(1)}</td>
                          <td className={`px-3 py-1.5 text-right font-mono ${info.constraint_violations > 0 ? 'text-danger' : 'text-ink/40'}`}>
                            {info.constraint_violations}
                          </td>
                          <td className="px-3 py-1.5 text-right font-mono text-ink/50">{info.total}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              {/* Gap results */}
              {feedbackData.gaps && feedbackData.gaps.length > 0 && (
                <div>
                  <h4 className="text-[11px] font-bold text-ink-bright mb-2 uppercase tracking-wider">Knowledge Gap Analysis</h4>
                  <div className="space-y-1">
                    {feedbackData.gaps.map((gap, idx) => (
                      <div key={idx} className={`p-2 border rounded-sm text-[10px] ${gapBg(gap)}`}>
                        <div className="flex items-center gap-2">
                          <span className={`font-bold ${gapColor(gap)}`}>
                            {gap.gap_type === 'training_density' ? '📊 Training Density' : '📚 Knowledge Gap'}
                          </span>
                          <span className="font-mono text-ink-bright">{gap.category}/{gap.concept}</span>
                        </div>
                        <div className="text-ink/60 mt-0.5">
                          Onyx results: {gap.onyx_result_count}
                          {gap.onyx_sources && gap.onyx_sources.length > 0 && (
                            <> — Sources: {gap.onyx_sources.join(', ')}</>
                          )}
                        </div>
                        <div className="text-ink/40 text-[9px] mt-0.5">
                          {gap.gap_type === 'training_density'
                            ? 'Onyx has relevant docs. Generate more training examples using --concept-focus.'
                            : 'No reference material found. Add a reference doc and re-index.'}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Trigger feedback */}
              <div className="border-t border-line pt-4">
                <button
                  onClick={() => setShowConfig(!showConfig)}
                  className="px-3 py-1.5 bg-warning/20 text-warning border border-warning/30 text-[11px] font-bold rounded-sm hover:bg-warning/30 transition-colors"
                >
                  {showConfig ? 'Hide Config ▲' : 'Trigger Feedback Loop ▼'}
                </button>

                {showConfig && (
                  <div className="mt-3 space-y-4">
                    {/* Thresholds section */}
                    <div className="p-3 bg-surface border border-line rounded-sm space-y-3">
                      <h5 className="text-[10px] font-bold text-ink/40 uppercase tracking-wider">Thresholds</h5>
                      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                        <div>
                          <label className="block text-[10px] font-bold text-ink/40 uppercase mb-1">
                            Win Rate Threshold: {fbConfig.winRateThreshold.toFixed(2)}
                          </label>
                          <input
                            type="range"
                            min={0} max={1} step={0.05}
                            value={fbConfig.winRateThreshold}
                            onChange={e => updateConfig('winRateThreshold', parseFloat(e.target.value))}
                            className="w-full accent-accent"
                          />
                        </div>
                        <div>
                          <label className="block text-[10px] font-bold text-ink/40 uppercase mb-1">
                            Quality Threshold: {fbConfig.qualityThreshold.toFixed(1)}
                          </label>
                          <input
                            type="range"
                            min={0} max={100} step={0.5}
                            value={fbConfig.qualityThreshold}
                            onChange={e => updateConfig('qualityThreshold', parseFloat(e.target.value))}
                            className="w-full accent-accent"
                          />
                        </div>
                        <div>
                          <label className="block text-[10px] font-bold text-ink/40 uppercase mb-1">Violation Threshold</label>
                          <input
                            type="number"
                            min={0} max={100}
                            value={fbConfig.violationThreshold}
                            onChange={e => updateConfig('violationThreshold', parseInt(e.target.value) || 1)}
                            className="w-20 bg-bg border border-line rounded px-2 py-1.5 text-[11px]"
                          />
                        </div>
                      </div>
                    </div>

                    {/* Execution modes */}
                    <div className="p-3 bg-surface border border-line rounded-sm space-y-3">
                      <h5 className="text-[10px] font-bold text-ink/40 uppercase tracking-wider">Execution Modes</h5>
                      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-[11px]">
                        <label className="flex items-center gap-2 cursor-pointer">
                          <input
                            type="checkbox"
                            checked={fbConfig.dryRun}
                            onChange={e => updateConfig('dryRun', e.target.checked)}
                          />
                          <span>Dry Run</span>
                        </label>
                        <label className="flex items-center gap-2 cursor-pointer">
                          <input
                            type="checkbox"
                            checked={fbConfig.skipGapDetection}
                            onChange={e => updateConfig('skipGapDetection', e.target.checked)}
                          />
                          <span>Skip Gap Detection</span>
                        </label>
                        <label className="flex items-center gap-2 cursor-pointer">
                          <input
                            type="checkbox"
                            checked={fbConfig.autoRetrain}
                            onChange={e => updateConfig('autoRetrain', e.target.checked)}
                          />
                          <span>Auto-Retrain</span>
                        </label>
                        <label className="flex items-center gap-2 cursor-pointer">
                          <input
                            type="checkbox"
                            checked={fbConfig.auto}
                            onChange={e => updateConfig('auto', e.target.checked)}
                          />
                          <span>Auto-Accept Decisions</span>
                        </label>
                      </div>
                      {fbConfig.autoRetrain && (
                        <div className="grid grid-cols-2 gap-3 text-[11px]">
                          <div>
                            <label className="block text-[10px] text-ink/40 mb-1">Train Preset</label>
                            <select
                              value={fbConfig.trainPreset}
                              onChange={e => updateConfig('trainPreset', e.target.value)}
                              className="bg-bg border border-line rounded px-2 py-1 text-[11px] w-full"
                            >
                              {TRAIN_PRESETS.map(tp => (
                                <option key={tp.value} value={tp.value}>{tp.label}</option>
                              ))}
                            </select>
                          </div>
                        </div>
                      )}
                    </div>

                    {/* Alternative Mode */}
                    <div className="p-3 bg-surface border border-line rounded-sm space-y-3">
                      <h5 className="text-[10px] font-bold text-ink/40 uppercase tracking-wider">Alternative Mode (without feedback.json)</h5>
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-[11px]">
                        <div>
                          <label className="block text-[10px] font-bold text-ink/40 uppercase mb-1">Spec</label>
                          <input
                            type="text"
                            value={fbConfig.spec}
                            onChange={e => updateConfig('spec', e.target.value)}
                            placeholder="subjects/NPC_specs/{npc}.json"
                            className="w-full bg-bg border border-line rounded px-2 py-1.5 text-[11px] font-mono"
                          />
                        </div>
                        <div>
                          <label className="block text-[10px] font-bold text-ink/40 uppercase mb-1">Candidate</label>
                          <input
                            type="text"
                            value={fbConfig.candidate}
                            onChange={e => updateConfig('candidate', e.target.value)}
                            placeholder="exports/{npc}/{npc}-lora-f16.gguf"
                            className="w-full bg-bg border border-line rounded px-2 py-1.5 text-[11px] font-mono"
                          />
                        </div>
                      </div>
                    </div>

                    {/* Regeneration Config */}
                    <div className="p-3 bg-surface border border-line rounded-sm space-y-3">
                      <h5 className="text-[10px] font-bold text-ink/40 uppercase tracking-wider">Regeneration Config</h5>
                      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3 text-[11px]">
                        <div>
                          <label className="block text-[10px] font-bold text-ink/40 uppercase mb-1">Technique</label>
                          <select
                            value={fbConfig.regenerationTechnique}
                            onChange={e => updateConfig('regenerationTechnique', e.target.value)}
                            className="w-full bg-bg border border-line rounded px-2 py-1.5 text-[11px]"
                          >
                            {REGEN_TECHNIQUES.map(rt => (
                              <option key={rt.value} value={rt.value}>{rt.label}</option>
                            ))}
                          </select>
                        </div>
                        <div>
                          <label className="block text-[10px] font-bold text-ink/40 uppercase mb-1">Preset</label>
                          <select
                            value={fbConfig.regenerationPreset}
                            onChange={e => updateConfig('regenerationPreset', e.target.value)}
                            className="w-full bg-bg border border-line rounded px-2 py-1.5 text-[11px]"
                          >
                            <option value="">Default</option>
                            {TRAIN_PRESETS.map(tp => (
                              <option key={tp.value} value={tp.value}>{tp.label}</option>
                            ))}
                          </select>
                        </div>
                        <div>
                          <label className="block text-[10px] font-bold text-ink/40 uppercase mb-1 flex items-center justify-between">
                            <span>Model</span>
                            {ollamaModels.loading && <RefreshCw className="w-3 h-3 animate-spin text-ink/30" />}
                          </label>
                          <div className="flex gap-1">
                            <select
                              value={ollamaModels.models.some(m => m.name === fbConfig.regenerationModel) || fbConfig.regenerationModel === '' ? fbConfig.regenerationModel : '__custom__'}
                              onChange={e => updateConfig('regenerationModel', e.target.value)}
                              className="w-full bg-bg border border-line rounded px-2 py-1.5 text-[11px]"
                            >
                              <option value="">Default</option>
                              {ollamaModels.models.map(m => <option key={m.name} value={m.name}>{m.name}</option>)}
                              <option value="__custom__">Custom…</option>
                            </select>
                            {(!ollamaModels.models.some(m => m.name === fbConfig.regenerationModel) && fbConfig.regenerationModel !== '') && (
                              <input
                                type="text"
                                value={fbConfig.regenerationModel === '__custom__' ? '' : fbConfig.regenerationModel}
                                onChange={e => updateConfig('regenerationModel', e.target.value)}
                                placeholder="qwen3:latest"
                                className="flex-1 bg-bg border border-accent/40 rounded px-2 py-1.5 text-[11px] font-mono"
                              />
                            )}
                          </div>
                        </div>
                        <div>
                          <label className="block text-[10px] font-bold text-ink/40 uppercase mb-1">URL</label>
                          <input
                            type="text"
                            value={fbConfig.regenerationUrl}
                            onChange={e => updateConfig('regenerationUrl', e.target.value)}
                            placeholder="http://localhost:11434"
                            className="w-full bg-bg border border-line rounded px-2 py-1.5 text-[11px] font-mono"
                          />
                        </div>
                        <div>
                          <label className="block text-[10px] font-bold text-ink/40 uppercase mb-1">Batch Size</label>
                          <input
                            type="number"
                            value={fbConfig.regenerationBatchSize}
                            onChange={e => updateConfig('regenerationBatchSize', parseInt(e.target.value) || 4)}
                            min={1} max={32}
                            className="w-20 bg-bg border border-line rounded px-2 py-1.5 text-[11px]"
                          />
                        </div>
                      </div>
                    </div>

                    {/* DeepEval Config */}
                    <div className="p-3 bg-surface border border-line rounded-sm space-y-3">
                      <h5 className="text-[10px] font-bold text-ink/40 uppercase tracking-wider">DeepEval Config</h5>
                      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3 text-[11px]">
                        <div>
                          <label className="block text-[10px] font-bold text-ink/40 uppercase mb-1">Judge Preset</label>
                          <select
                            value={fbConfig.deepevalJudgePreset}
                            onChange={e => updateConfig('deepevalJudgePreset', e.target.value)}
                            className="w-full bg-bg border border-line rounded px-2 py-1.5 text-[11px]"
                          >
                            {JUDGE_PRESETS.map(jp => (
                              <option key={jp.value} value={jp.value}>{jp.label}</option>
                            ))}
                          </select>
                        </div>
                        <div>
                          <label className="block text-[10px] font-bold text-ink/40 uppercase mb-1 flex items-center justify-between">
                            <span>Judge Model</span>
                            {ollamaModels.loading && <RefreshCw className="w-3 h-3 animate-spin text-ink/30" />}
                          </label>
                          <div className="flex gap-1">
                            <select
                              value={ollamaModels.models.some(m => m.name === fbConfig.deepevalJudgeModel) || fbConfig.deepevalJudgeModel === '' ? fbConfig.deepevalJudgeModel : '__custom__'}
                              onChange={e => updateConfig('deepevalJudgeModel', e.target.value)}
                              className="w-full bg-bg border border-line rounded px-2 py-1.5 text-[11px]"
                            >
                              <option value="">Default</option>
                              {ollamaModels.models.map(m => <option key={m.name} value={m.name}>{m.name}</option>)}
                              <option value="__custom__">Custom…</option>
                            </select>
                            {(!ollamaModels.models.some(m => m.name === fbConfig.deepevalJudgeModel) && fbConfig.deepevalJudgeModel !== '') && (
                              <input
                                type="text"
                                value={fbConfig.deepevalJudgeModel === '__custom__' ? '' : fbConfig.deepevalJudgeModel}
                                onChange={e => updateConfig('deepevalJudgeModel', e.target.value)}
                                placeholder="qwen3:latest"
                                className="flex-1 bg-bg border border-accent/40 rounded px-2 py-1.5 text-[11px] font-mono"
                              />
                            )}
                          </div>
                        </div>
                        <div>
                          <label className="block text-[10px] font-bold text-ink/40 uppercase mb-1">Ollama URL</label>
                          <input
                            type="text"
                            value={fbConfig.deepevalOllamaUrl}
                            onChange={e => updateConfig('deepevalOllamaUrl', e.target.value)}
                            placeholder="http://localhost:11434"
                            className="w-full bg-bg border border-line rounded px-2 py-1.5 text-[11px] font-mono"
                          />
                        </div>
                        <div>
                          <label className="block text-[10px] font-bold text-ink/40 uppercase mb-1">Cases per Category</label>
                          <input
                            type="number"
                            value={fbConfig.deepevalCasesPerCategory}
                            onChange={e => updateConfig('deepevalCasesPerCategory', parseInt(e.target.value) || 1)}
                            min={1} max={20}
                            className="w-20 bg-bg border border-line rounded px-2 py-1.5 text-[11px]"
                          />
                        </div>
                        <div className="flex items-end gap-3">
                          <label className="flex items-center gap-2 cursor-pointer">
                            <input
                              type="checkbox"
                              checked={fbConfig.deepevalSoftFail}
                              onChange={e => updateConfig('deepevalSoftFail', e.target.checked)}
                            />
                            <span>Soft Fail</span>
                          </label>
                          <label className="flex items-center gap-2 cursor-pointer">
                            <input
                              type="checkbox"
                              checked={fbConfig.skipDatasetEval}
                              onChange={e => updateConfig('skipDatasetEval', e.target.checked)}
                            />
                            <span>Skip Dataset Eval</span>
                          </label>
                        </div>
                      </div>
                    </div>

                    {/* Output options */}
                    <div className="p-3 bg-surface border border-line rounded-sm space-y-3">
                      <h5 className="text-[10px] font-bold text-ink/40 uppercase tracking-wider">Output Options</h5>
                      <div className="flex items-end gap-4 text-[11px]">
                        <label className="flex items-center gap-2 cursor-pointer">
                          <input
                            type="checkbox"
                            checked={fbConfig.saveGaps}
                            onChange={e => updateConfig('saveGaps', e.target.checked)}
                          />
                          <span>Save Gaps to File</span>
                        </label>
                        <label className="flex items-center gap-2 cursor-pointer">
                          <input
                            type="checkbox"
                            checked={fbConfig.json}
                            onChange={e => updateConfig('json', e.target.checked)}
                          />
                          <span>JSON Output</span>
                        </label>
                      </div>
                    </div>

                    <button
                      onClick={handleRunFeedback}
                      disabled={running}
                      className="px-4 py-2 bg-accent text-bg text-[12px] font-bold rounded-sm hover:brightness-110 transition-colors disabled:opacity-40"
                    >
                      {running ? 'Running…' : 'Execute Feedback'}
                    </button>
                  </div>
                )}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
};
