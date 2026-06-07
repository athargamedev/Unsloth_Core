import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { fetchOptionalJson } from '../api';
import type { Subject, ExportArtifact } from '../api';
import { EvalReportsDataSchema } from '../schemas/eval-reports';
import type { ValidatedEvalReportsData, EvalReportFile } from '../schemas/eval-reports';
import { useOllamaModels } from '../hooks/useOllamaModels';
import { RefreshCw } from 'lucide-react';
import { FieldRenderer } from './FieldRenderer';

interface EvalConfig {
  npcKey: string;
  spec: string;
  baseline: string;
  candidate: string;
  baseModel: string;
  loraWeight: number;
  numQuestions: number;
  reportHtml: boolean;
  track: boolean;
  feedbackJson: string;
  judge: boolean;
  judgeModel: string;
  // New fields
  model: string;
  wandb: boolean;
  wandbProject: string;
  wandbEntity: string;
  host: string;
  port: number;
  gpuLayers: number;
  maxTokens: number;
  interactive: boolean;
  trainingMetrics: boolean;
  trainingMetricsPath: string;
  output: string;
  valData: string;
}

const DEFAULT_BASE = '/home/athar/Setup Guide In-Editor Tutorial/Assets/StreamingAssets/Models/llama-3.2-3b-instruct-q4_k_m.gguf';
const DEFAULT_JUDGE_MODEL = 'qwen2.5:7b';

type EvalMode = 'compare' | 'single';

export const EvalWorkflowPanel = ({
  subjects, exportArtifacts, evaluateSchema,
}: {
  subjects: Subject[];
  exportArtifacts: ExportArtifact[];
  evaluateSchema: Record<string, any>;
}) => {
  const ollamaModels = useOllamaModels();
  const [config, setConfig] = useState<EvalConfig>({
    npcKey: '',
    spec: '',
    baseline: DEFAULT_BASE,
    candidate: '',
    baseModel: DEFAULT_BASE,
    loraWeight: 1.0,
    numQuestions: 10,
    reportHtml: true,
    track: true,
    feedbackJson: '',
    judge: false,
    judgeModel: DEFAULT_JUDGE_MODEL,
    // New fields defaults
    model: '',
    wandb: false,
    wandbProject: 'unsloth-core',
    wandbEntity: '',
    host: '127.0.0.1',
    port: 8888,
    gpuLayers: 99,
    maxTokens: 256,
    interactive: false,
    trainingMetrics: false,
    trainingMetricsPath: '',
    output: '',
    valData: '',
  });
  const [evalMode, setEvalMode] = useState<EvalMode>('compare');
  const [apiError, setApiError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [selectedReportHtml, setSelectedReportHtml] = useState<string | null>(null);
  const [activeReportFile, setActiveReportFile] = useState<EvalReportFile | null>(null);
  const pendingReportNpcKey = useRef<string | null>(null);
  const [pendingNpcState, setPendingNpcState] = useState<string | null>(null); // To trigger effect
  const [lastEvalTime, setLastEvalTime] = useState<number>(0);
  const iframeRef = useRef<HTMLIFrameElement>(null);
  
  // 2. React Query Usage for polling Eval Reports with Zod
  const { data: reports, refetch: refreshReports, error: reportsError } = useQuery<ValidatedEvalReportsData | null, Error>({
    queryKey: ['eval-reports-polling'],
    queryFn: async () => {
      const rawData = await fetchOptionalJson<unknown>('/api/eval-reports');
      if (!rawData) return null;
      return EvalReportsDataSchema.parse(rawData);
    },
    refetchInterval: 5000, // Automates the manual setInterval polling!
  });
  const pendingReportAttempts = useRef(0);

  // Load subjects, presets, reports
  useEffect(() => {
    setConfig(prev => {
      const firstSubject = subjects[0];
      if (firstSubject && !prev.npcKey) {
        return {
          ...prev,
          npcKey: firstSubject.id,
          spec: firstSubject.path || `subjects/${firstSubject.id}.json`,
        };
      }
      return prev;
    });
  }, [subjects]);

  // Polling logic is now handled by React Query's refetchInterval!

  useEffect(() => {
    if (!pendingNpcState || !reports) return;
    const group = reports.reports.find(r => r.npcKey === pendingNpcState);
    const latestHtml = group?.files.find(file => file.name.endsWith('.html')) || null;
    if (!latestHtml) {
      if (pendingReportAttempts.current < 15) {
        pendingReportAttempts.current += 1;
        const timer = window.setTimeout(() => {
          void refreshReports();
        }, 1000);
        return () => window.clearTimeout(timer);
      }
      return;
    }
    pendingReportAttempts.current = 0;
    void loadReportHtml(latestHtml);
    setPendingNpcState(null);
    pendingReportNpcKey.current = null;
  }, [pendingNpcState, reports, refreshReports]);

  // Pick candidate from exports when npcKey changes
  useEffect(() => {
    if (!config.npcKey) return;
    const matchingExport = exportArtifacts.find(e => e.npcKey === config.npcKey);
    if (matchingExport) {
      setConfig(prev => ({
        ...prev,
        baseline: prev.baseline || DEFAULT_BASE,
        candidate: matchingExport.file,
        feedbackJson: `eval/results/feedback/${config.npcKey}.json`,
      }));
    }
  }, [config.npcKey, exportArtifacts]);

  // When a report is served, we need to get the actual HTML content
  const loadReportHtml = async (file: EvalReportFile) => {
    setActiveReportFile(file);
    try {
      const resp = await fetch(`/api/eval-reports/file?path=${encodeURIComponent(file.path)}`);
      if (!resp.ok) {
        setApiError(`Failed to load report: ${resp.statusText}`);
        return;
      }
      const html = await resp.text();
      setSelectedReportHtml(html);
    } catch (err) {
      setApiError(err instanceof Error ? err.message : 'Failed to load report');
    }
  };

  const handleViewReport = async (file: EvalReportFile) => {
    await loadReportHtml(file);
  };

  const handleRunEval = async () => {
    if (evalMode === 'compare') {
      const baseline = config.baseline.trim() || config.baseModel.trim() || DEFAULT_BASE;
      const candidate = config.candidate.trim();
      if (!config.spec || !baseline || !candidate) {
        setApiError('Spec, baseline, and candidate are required');
        return;
      }
    } else {
      if (!config.model.trim()) {
        setApiError('Model path is required in single model mode');
        return;
      }
    }
    setRunning(true);
    setApiError(null);
    try {
      const payload: Record<string, unknown> = {
        commandId: 'evaluate',
        type: 'Evaluation',
        spec: config.spec,
        options: {},
      };

      if (evalMode === 'single') {
        payload.options = {
          ...(payload.options as Record<string, unknown>),
          model: config.model,
        };
      } else {
        const baseline = config.baseline.trim() || config.baseModel.trim() || DEFAULT_BASE;
        payload.options = {
          ...(payload.options as Record<string, unknown>),
          baseline,
          candidate: config.candidate,
        };
        if (config.baseModel) {
          payload['base-model'] = config.baseModel;
          payload.options = {
            ...(payload.options as Record<string, unknown>),
            baseModel: config.baseModel,
          };
        }
        if (config.loraWeight) {
          payload.options = {
            ...(payload.options as Record<string, unknown>),
            loraWeight: config.loraWeight,
          };
        }
      }

      // Common options
      const opts = payload.options as Record<string, unknown>;
      opts.numQuestions = config.numQuestions;
      opts.reportHtml = config.reportHtml;
      opts.track = config.track;

      // W&B
      opts.wandb = config.wandb;
      if (config.wandbProject) opts.wandbProject = config.wandbProject;
      if (config.wandbEntity) opts.wandbEntity = config.wandbEntity;

      // Inference server
      opts.host = config.host;
      opts.port = config.port;
      opts.gpuLayers = config.gpuLayers;
      opts.maxTokens = config.maxTokens;

      // Judge
      if (config.judge) {
        opts.judge = true;
        opts.judgeModel = config.judgeModel;
      }

      // Interactive
      if (config.interactive) opts.interactive = true;

      // Training metrics (nargs="?" special handling)
      if (config.trainingMetrics) {
        if (config.trainingMetricsPath.trim()) {
          payload.trainingMetrics = config.trainingMetricsPath.trim();
          opts.trainingMetrics = config.trainingMetricsPath.trim();
        } else {
          payload.trainingMetrics = true;
          opts.trainingMetrics = true;
        }
      }

      // Feedback JSON
      if (config.feedbackJson) {
        payload['feedback-json'] = config.feedbackJson;
        opts.feedbackJson = config.feedbackJson;
      }

      // Output
      if (config.output) {
        payload.output = config.output;
        opts.output = config.output;
      }

      // Val data
      if (config.valData) {
        opts.valData = config.valData;
      }

      // NPC key
      opts.npcKey = config.npcKey;

      const response = await fetch('/api/commands/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!response.ok) {
        const err = await response.json().catch(() => ({}));
        throw new Error(err.error || 'Failed to start evaluation');
      }
      setLastEvalTime(Date.now());
      pendingReportAttempts.current = 0;
      pendingReportNpcKey.current = config.npcKey;
      setPendingNpcState(config.npcKey);
    } catch (err) {
      setApiError(err instanceof Error ? err.message : 'Evaluation failed');
    } finally {
      setRunning(false);
    }
  };

  const handleNpcChange = (npcKey: string) => {
    const subject = subjects.find(s => s.id === npcKey);
    setConfig(prev => ({
      ...prev,
      npcKey,
      spec: subject?.path || `subjects/${npcKey}.json`,
      candidate: '',
      feedbackJson: `eval/results/feedback/${npcKey}.json`,
    }));
  };

  // Unpack what .html reports are available
  const reportFiles: EvalReportFile[] = reports
    ? reports.reports.flatMap(g => g.files)
    : [];

  const updateOpt = <K extends keyof EvalConfig>(key: K, value: EvalConfig[K]) => {
    setConfig(prev => ({ ...prev, [key]: value }));
  };

  const templateContext = useMemo(() => ({
    npcKey: config.npcKey || '',
    technique: 'ollama',
  }), [config.npcKey]);

  const schemaPathToEvalConfig: Record<string, keyof EvalConfig | undefined> = {
    'options.baseModel': 'baseModel',
    'options.numQuestions': 'numQuestions',
    'options.loraWeight': 'loraWeight',
    'options.valData': 'valData',
    'options.wandb': 'wandb',
    'options.wandbProject': 'wandbProject',
    'options.wandbEntity': 'wandbEntity',
    'options.host': 'host',
    'options.port': 'port',
    'options.gpuLayers': 'gpuLayers',
    'options.maxTokens': 'maxTokens',
    'options.reportHtml': 'reportHtml',
    'options.track': 'track',
    'options.judge': 'judge',
    'options.feedbackJson': 'feedbackJson',
    'options.output': 'output',
    'options.interactive': 'interactive',
  };

  const handleFieldChange = useCallback((fieldPath: string, value: unknown) => {
    const configKey = schemaPathToEvalConfig[fieldPath];
    if (configKey) {
      setConfig(prev => ({ ...prev, [configKey]: value as EvalConfig[typeof configKey] }));
    }
  }, []);

  return (
    <div className="flex-1 flex flex-col overflow-hidden min-h-0 min-w-0">
      {/* Top config panel */}
      <div className="p-4 border-b border-line bg-surface/30 space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="text-xs font-bold text-ink-bright uppercase tracking-widest">Evaluate Model</h3>
          <div className="flex gap-2">
            <button
              onClick={handleRunEval}
              disabled={running || !config.spec}
              className="px-4 py-2 bg-accent text-bg text-[12px] font-bold rounded-sm hover:brightness-110 transition-colors disabled:opacity-40 flex items-center gap-2"
            >
              {running ? (
                <><span className="w-3 h-3 border-2 border-bg border-t-transparent rounded-full animate-spin" /> Running…</>
              ) : 'Run Evaluation'}
            </button>
          </div>
        </div>

        {(apiError || reportsError) && (
          <div className="p-2 bg-danger/10 border border-danger/30 rounded text-[11px] text-danger">
            {apiError || reportsError?.message}
          </div>
        )}

        {/* Mode Toggle */}
        <div className="flex items-center gap-4 border-b border-line pb-3">
          <span className="text-[10px] font-bold text-ink/40 uppercase">Mode:</span>
          <label className="flex items-center gap-1.5 cursor-pointer">
            <input
              type="radio"
              name="evalMode"
              checked={evalMode === 'compare'}
              onChange={() => setEvalMode('compare')}
              className="accent-accent"
            />
            <span className="text-[11px] font-medium">Compare (Baseline + Candidate)</span>
          </label>
          <label className="flex items-center gap-1.5 cursor-pointer">
            <input
              type="radio"
              name="evalMode"
              checked={evalMode === 'single'}
              onChange={() => setEvalMode('single')}
              className="accent-accent"
            />
            <span className="text-[11px] font-medium">Single Model</span>
          </label>
        </div>

        {/* Config grid */}
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3 text-[11px]">
          {/* NPC / Spec */}
          <div>
            <label className="block text-[10px] font-bold text-ink/40 uppercase mb-1">NPC Subject</label>
            <select
              value={config.npcKey}
              onChange={e => handleNpcChange(e.target.value)}
              className="w-full bg-bg border border-line rounded px-2 py-1.5 text-[11px]"
            >
              <option value="">Select NPC…</option>
              {subjects.map(s => <option key={s.id} value={s.id}>{s.id}</option>)}
            </select>
          </div>

          {/* Model Selection - changes based on mode */}
          {evalMode === 'single' ? (
            <div className="sm:col-span-2 xl:col-span-3">
              <label className="block text-[10px] font-bold text-ink/40 uppercase mb-1 flex items-center justify-between">
                <span>Model GGUF Path or Ollama Model</span>
                {ollamaModels.loading && <RefreshCw className="w-3 h-3 animate-spin text-ink/30" />}
              </label>
              <div className="flex gap-1">
                <select
                  value={ollamaModels.models.some(m => m.name === config.model) || config.model === '' ? config.model : '__custom__'}
                  onChange={e => updateOpt('model', e.target.value)}
                  className="bg-bg border border-line rounded px-2 py-1.5 text-[11px] min-w-[140px]"
                >
                  <option value="">Select Ollama Model…</option>
                  {ollamaModels.models.map(m => <option key={m.name} value={m.name}>{m.name}</option>)}
                  <option value="__custom__">Custom Path…</option>
                </select>
                {(!ollamaModels.models.some(m => m.name === config.model) && config.model !== '') && (
                  <input
                    type="text"
                    value={config.model === '__custom__' ? '' : config.model}
                    onChange={e => updateOpt('model', e.target.value)}
                    placeholder="/path/to/model.gguf or exports/{npc}/{npc}-lora-f16.gguf"
                    className="flex-1 bg-bg border border-accent/40 rounded px-2 py-1.5 text-[11px] font-mono"
                  />
                )}
              </div>
            </div>
          ) : (
            <>
              {/* Baseline */}
              <div>
                <label className="block text-[10px] font-bold text-ink/40 uppercase mb-1">Baseline GGUF</label>
                <input
                  type="text"
                  value={config.baseline}
                  onChange={e => updateOpt('baseline', e.target.value)}
                  placeholder="/path/to/base.gguf or previous full-merge"
                  className="w-full bg-bg border border-line rounded px-2 py-1.5 text-[11px] font-mono"
                />
              </div>

              {/* Candidate */}
              <div>
                <label className="block text-[10px] font-bold text-ink/40 uppercase mb-1">Candidate Adapter</label>
                <div className="flex gap-1">
                  <input
                    type="text"
                    value={config.candidate}
                    onChange={e => updateOpt('candidate', e.target.value)}
                    placeholder="exports/{npc}/{npc}-lora-f16.gguf"
                    className="flex-1 bg-bg border border-line rounded px-2 py-1.5 text-[11px] font-mono"
                  />
                  <select
                    value={config.candidate}
                    onChange={e => updateOpt('candidate', e.target.value)}
                    className="bg-bg border border-line rounded px-1 text-[10px]"
                  >
                    <option value="">Pick…</option>
                    {exportArtifacts.filter(e => !config.npcKey || e.npcKey === config.npcKey).map(e => (
                      <option key={e.file} value={e.file}>{e.npcKey}/{e.file.split('/').pop()}</option>
                    ))}
                  </select>
                </div>
              </div>
            </>
          )}
        </div>

        {/* Section: Base Config */}
        <details className="group" open>
          <summary className="text-[10px] font-bold text-ink/40 uppercase tracking-widest cursor-pointer select-none group-open:text-ink/60">
            Base Config
          </summary>
          <div className="mt-3 grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3 text-[11px]">
            <div>
              <FieldRenderer
                fieldPath="options.baseModel"
                schema={evaluateSchema['options.baseModel']}
                value={config.baseModel}
                onChange={handleFieldChange}
                context={templateContext}
              />
            </div>
            <div>
              <FieldRenderer
                fieldPath="options.numQuestions"
                schema={evaluateSchema['options.numQuestions']}
                value={config.numQuestions}
                onChange={handleFieldChange}
                context={templateContext}
              />
            </div>
            <div>
              <FieldRenderer
                fieldPath="options.loraWeight"
                schema={evaluateSchema['options.loraWeight']}
                value={config.loraWeight}
                onChange={handleFieldChange}
                context={templateContext}
              />
            </div>
            <div>
              <FieldRenderer
                fieldPath="options.valData"
                schema={evaluateSchema['options.valData']}
                value={config.valData}
                onChange={handleFieldChange}
                context={templateContext}
              />
            </div>
          </div>
        </details>

        {/* Section: W&B Config */}
        <details className="group">
          <summary className="text-[10px] font-bold text-ink/40 uppercase tracking-widest cursor-pointer select-none group-open:text-ink/60">
            W&B Tracking
          </summary>
          <div className="mt-3 grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3 text-[11px]">
            <div>
              <FieldRenderer
                fieldPath="options.wandb"
                schema={evaluateSchema['options.wandb']}
                value={config.wandb}
                onChange={handleFieldChange}
                context={templateContext}
              />
            </div>
            <div>
              <FieldRenderer
                fieldPath="options.wandbProject"
                schema={evaluateSchema['options.wandbProject']}
                value={config.wandbProject}
                onChange={handleFieldChange}
                context={templateContext}
              />
            </div>
            <div>
              <FieldRenderer
                fieldPath="options.wandbEntity"
                schema={evaluateSchema['options.wandbEntity']}
                value={config.wandbEntity}
                onChange={handleFieldChange}
                context={templateContext}
              />
            </div>
          </div>
        </details>

        {/* Section: Inference Server */}
        <details className="group">
          <summary className="text-[10px] font-bold text-ink/40 uppercase tracking-widest cursor-pointer select-none group-open:text-ink/60">
            Inference Server (llama.cpp)
          </summary>
          <div className="mt-3 grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3 text-[11px]">
            <div>
              <FieldRenderer
                fieldPath="options.host"
                schema={evaluateSchema['options.host']}
                value={config.host}
                onChange={handleFieldChange}
                context={templateContext}
              />
            </div>
            <div>
              <FieldRenderer
                fieldPath="options.port"
                schema={evaluateSchema['options.port']}
                value={config.port}
                onChange={handleFieldChange}
                context={templateContext}
              />
            </div>
            <div>
              <FieldRenderer
                fieldPath="options.gpuLayers"
                schema={evaluateSchema['options.gpuLayers']}
                value={config.gpuLayers}
                onChange={handleFieldChange}
                context={templateContext}
              />
            </div>
            <div>
              <FieldRenderer
                fieldPath="options.maxTokens"
                schema={evaluateSchema['options.maxTokens']}
                value={config.maxTokens}
                onChange={handleFieldChange}
                context={templateContext}
              />
            </div>
          </div>
        </details>

        {/* Section: Output Options */}
        <details className="group">
          <summary className="text-[10px] font-bold text-ink/40 uppercase tracking-widest cursor-pointer select-none group-open:text-ink/60">
            Output Options
          </summary>
          <div className="mt-3 grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3 text-[11px]">
            <div>
              <FieldRenderer
                fieldPath="options.reportHtml"
                schema={evaluateSchema['options.reportHtml']}
                value={config.reportHtml}
                onChange={handleFieldChange}
                context={templateContext}
              />
            </div>
            <div>
              <FieldRenderer
                fieldPath="options.track"
                schema={evaluateSchema['options.track']}
                value={config.track}
                onChange={handleFieldChange}
                context={templateContext}
              />
            </div>
            <div>
              <FieldRenderer
                fieldPath="options.judge"
                schema={evaluateSchema['options.judge']}
                value={config.judge}
                onChange={handleFieldChange}
                context={templateContext}
              />
            </div>
            <div>
              <label className="block text-[10px] font-bold text-ink/40 uppercase mb-1 flex items-center justify-between">
                <span>Judge Model</span>
                {ollamaModels.loading && <RefreshCw className="w-3 h-3 animate-spin text-ink/30" />}
              </label>
              <div className="flex gap-1">
                <select
                  value={ollamaModels.models.some(m => m.name === config.judgeModel) || config.judgeModel === '' ? config.judgeModel : '__custom__'}
                  onChange={e => updateOpt('judgeModel', e.target.value)}
                  className="bg-bg border border-line rounded px-2 py-1.5 text-[11px] flex-1"
                >
                  <option value="">{DEFAULT_JUDGE_MODEL}</option>
                  {ollamaModels.models.map(m => <option key={m.name} value={m.name}>{m.name}</option>)}
                  <option value="__custom__">Custom…</option>
                </select>
                {(!ollamaModels.models.some(m => m.name === config.judgeModel) && config.judgeModel !== '') && (
                  <input
                    type="text"
                    value={config.judgeModel === '__custom__' ? '' : config.judgeModel}
                    onChange={e => updateOpt('judgeModel', e.target.value)}
                    placeholder={DEFAULT_JUDGE_MODEL}
                    className="w-20 bg-bg border border-accent/40 rounded px-2 py-1.5 text-[11px] font-mono"
                  />
                )}
              </div>
            </div>
            <div>
              <FieldRenderer
                fieldPath="options.feedbackJson"
                schema={evaluateSchema['options.feedbackJson']}
                value={config.feedbackJson}
                onChange={handleFieldChange}
                context={templateContext}
              />
            </div>
            <div>
              <FieldRenderer
                fieldPath="options.output"
                schema={evaluateSchema['options.output']}
                value={config.output}
                onChange={handleFieldChange}
                context={templateContext}
              />
            </div>
          </div>
        </details>

        {/* Section: Advanced */}
        <details className="group">
          <summary className="text-[10px] font-bold text-ink/40 uppercase tracking-widest cursor-pointer select-none group-open:text-ink/60">
            Advanced
          </summary>
          <div className="mt-3 grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3 text-[11px]">
            <div>
              <FieldRenderer
                fieldPath="options.interactive"
                schema={evaluateSchema['options.interactive']}
                value={config.interactive}
                onChange={handleFieldChange}
                context={templateContext}
              />
            </div>

            {/* Training Metrics: checkbox + optional path */}
            <div>
              <label className="block text-[10px] font-bold text-ink/40 uppercase mb-1">Training Metrics</label>
              <div className="flex gap-2 items-center">
                <label className="flex items-center gap-1.5 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={config.trainingMetrics}
                    onChange={e => updateOpt('trainingMetrics', e.target.checked)}
                  />
                  <span className="text-[10px] text-ink/60">Pass flag</span>
                </label>
                {config.trainingMetrics && (
                  <input
                    type="text"
                    value={config.trainingMetricsPath}
                    onChange={e => updateOpt('trainingMetricsPath', e.target.value)}
                    placeholder="/path/to/metrics.json (optional)"
                    className="flex-1 bg-bg border border-line rounded px-2 py-1 text-[11px] font-mono"
                  />
                )}
              </div>
              <div className="text-[8px] text-ink/30 mt-0.5">
                {config.trainingMetrics
                  ? config.trainingMetricsPath
                    ? `Passes: --training-metrics ${config.trainingMetricsPath}`
                    : 'Passes: --training-metrics (flag only)'
                  : 'Not passed'}
              </div>
            </div>
          </div>
        </details>
      </div>

      {/* Results area: reports list + inline HTML viewer */}
      <div className="flex flex-col xl:flex-row flex-1 overflow-hidden min-h-0 min-w-0">
        {/* Report sidebar */}
        <div className="w-56 border-r border-line overflow-y-auto p-2 space-y-1 custom-scrollbar bg-surface/20">
          <div className="text-[10px] font-bold text-ink/40 uppercase tracking-widest px-2 py-1">Reports</div>
          {reportFiles.length === 0 && (
            <div className="text-[10px] text-ink/30 px-2 py-4 text-center">No reports yet</div>
          )}
          {reportFiles
            .filter(f => f.name.endsWith('.html'))
            .map((file, idx) => (
              <button
                key={`${file.name}-${idx}`}
                onClick={() => handleViewReport(file)}
                className={`w-full text-left px-2 py-1.5 text-[10px] font-mono rounded transition-colors ${
                  activeReportFile?.path === file.path
                    ? 'bg-accent/20 text-accent border border-accent/30'
                    : 'hover:bg-line/20 text-ink/70'
                }`}
              >
                <div className="truncate">{file.name}</div>
                <div className="text-[8px] text-ink/30">{file.path.split('/')[1]}/{file.path.split('/')[2]}</div>
              </button>
            ))}
        </div>

        {/* Report viewer */}
        <div className="flex-1 bg-white">
          {selectedReportHtml ? (
            <iframe
              ref={iframeRef}
              srcDoc={selectedReportHtml}
              className="w-full h-full border-0"
              title="Eval Report"
              sandbox="allow-scripts"
            />
          ) : (
            <div className="h-full flex items-center justify-center text-ink/30">
              <div className="text-center space-y-2">
                <div className="text-[12px] font-bold uppercase tracking-widest">Eval Report Viewer</div>
                <div className="text-[10px]">Select an HTML report from the sidebar</div>
                <div className="text-[9px] text-ink/20 italic">Reports appear here after running evaluation with --report-html</div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
