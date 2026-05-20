import { useState, useEffect, useRef, useCallback } from 'react';
import { fetchJson, fetchOptionalJson } from '../api';
import type { Subject, ExportArtifact, EvalReportsData, EvalReportFile } from '../api';

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
}

const DEFAULT_BASE = '/home/athar/Setup Guide In-Editor Tutorial/Assets/StreamingAssets/Models/llama-3.2-3b-instruct-q4_k_m.gguf';
const DEFAULT_JUDGE_MODEL = 'qwen2.5:7b';

export const EvalWorkflowPanel = ({
  subjects, exportArtifacts,
}: {
  subjects: Subject[];
  exportArtifacts: ExportArtifact[];
}) => {
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
  });
  const [apiError, setApiError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [reports, setReports] = useState<EvalReportsData | null>(null);
  const [selectedReportHtml, setSelectedReportHtml] = useState<string | null>(null);
  const [activeReportFile, setActiveReportFile] = useState<EvalReportFile | null>(null);
  const [pendingReportNpcKey, setPendingReportNpcKey] = useState<string | null>(null);
  const [presets, setPresets] = useState<Array<{ name: string; description: string; path?: string }>>([]);
  const [lastEvalTime, setLastEvalTime] = useState<number>(0);
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const refreshReports = useCallback(async () => {
    const data = await fetchOptionalJson<EvalReportsData>('/api/eval-reports');
    if (data) setReports(data);
  }, []);
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

  useEffect(() => {
    const loadPresets = async () => {
      const data = await fetchOptionalJson<Array<{ name: string; description: string; path?: string }>>('/api/presets');
      if (data) setPresets(data);
    };
    loadPresets();
  }, []);

  useEffect(() => {
    refreshReports();
    const interval = setInterval(() => {
      void refreshReports();
    }, 1000);
    return () => clearInterval(interval);
  }, [refreshReports]);

  useEffect(() => {
    if (!pendingReportNpcKey || !reports) return;
    const group = reports.reports.find(r => r.npcKey === pendingReportNpcKey);
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
    setPendingReportNpcKey(null);
  }, [pendingReportNpcKey, reports, refreshReports]);

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
    const baseline = config.baseline.trim() || config.baseModel.trim() || DEFAULT_BASE;
    const candidate = config.candidate.trim();
    if (!config.spec || !baseline || !candidate) {
      setApiError('Spec, baseline, and candidate are required');
      return;
    }
    setRunning(true);
    setApiError(null);
    try {
      const payload: Record<string, unknown> = {
        commandId: 'evaluate',
        type: 'Evaluation',
        baseline,
        candidate,
        spec: config.spec,
        options: {
          baseline,
          candidate,
          baseModel: config.baseModel,
          loraWeight: config.loraWeight,
          numQuestions: config.numQuestions,
          reportHtml: config.reportHtml,
          track: config.track,
          feedbackJson: config.feedbackJson,
          judge: config.judge,
          judgeModel: config.judgeModel,
        },
      };
      if (config.baseModel) {
        payload['base-model'] = config.baseModel;
      }
      if (config.feedbackJson) {
        payload['feedback-json'] = config.feedbackJson;
      }
      if (config.judge) payload.judge = true;

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
      setPendingReportNpcKey(config.npcKey);
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

  return (
    <div className="flex-1 flex flex-col overflow-hidden min-h-0 min-w-0">
      {/* Top config panel */}
      <div className="p-4 border-b border-line bg-surface/30 space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="text-xs font-bold text-ink-bright uppercase tracking-widest">Evaluate Model</h3>
          <div className="flex gap-2">
            <button
              onClick={handleRunEval}
              disabled={running || !config.spec || !config.candidate}
              className="px-4 py-2 bg-accent text-bg text-[12px] font-bold rounded-sm hover:brightness-110 transition-colors disabled:opacity-40 flex items-center gap-2"
            >
              {running ? (
                <><span className="w-3 h-3 border-2 border-bg border-t-transparent rounded-full animate-spin" /> Running…</>
              ) : 'Run Evaluation'}
            </button>
          </div>
        </div>

        {apiError && (
          <div className="p-2 bg-danger/10 border border-danger/30 rounded text-[11px] text-danger">{apiError}</div>
        )}

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

          {/* Baseline */}
          <div>
            <label className="block text-[10px] font-bold text-ink/40 uppercase mb-1">Baseline GGUF</label>
            <input
              type="text"
              value={config.baseline}
              onChange={e => setConfig(prev => ({ ...prev, baseline: e.target.value }))}
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
                onChange={e => setConfig(prev => ({ ...prev, candidate: e.target.value }))}
                placeholder="exports/{npc}/{npc}-lora-f16.gguf"
                className="flex-1 bg-bg border border-line rounded px-2 py-1.5 text-[11px] font-mono"
              />
              <select
                value={config.candidate}
                onChange={e => setConfig(prev => ({ ...prev, candidate: e.target.value }))}
                className="bg-bg border border-line rounded px-1 text-[10px]"
              >
                <option value="">Pick…</option>
                {exportArtifacts.filter(e => !config.npcKey || e.npcKey === config.npcKey).map(e => (
                  <option key={e.file} value={e.file}>{e.npcKey}/{e.file.split('/').pop()}</option>
                ))}
              </select>
            </div>
          </div>

          {/* Base model (LoRA mode) */}
          <div>
            <label className="block text-[10px] font-bold text-ink/40 uppercase mb-1">Base Model <span className="text-accent">(LoRA)</span></label>
            <input
              type="text"
              value={config.baseModel}
              onChange={e => setConfig(prev => ({ ...prev, baseModel: e.target.value }))}
              placeholder={DEFAULT_BASE}
              className="w-full bg-bg border border-line rounded px-2 py-1.5 text-[11px] font-mono"
            />
            <div className="text-[8px] text-ink/30 mt-0.5">Required when candidate is a LoRA adapter</div>
          </div>

          {/* Options */}
          <div>
            <label className="block text-[10px] font-bold text-ink/40 uppercase mb-1">Questions</label>
            <input
              type="number"
              value={config.numQuestions}
              onChange={e => setConfig(prev => ({ ...prev, numQuestions: parseInt(e.target.value) || 10 }))}
              min={1} max={50}
              className="w-20 bg-bg border border-line rounded px-2 py-1.5 text-[11px]"
            />
          </div>

          <div>
            <label className="block text-[10px] font-bold text-ink/40 uppercase mb-1">LoRA Weight</label>
            <input
              type="number"
              value={config.loraWeight}
              onChange={e => setConfig(prev => ({ ...prev, loraWeight: parseFloat(e.target.value) || 1.0 }))}
              min={0} max={2} step={0.1}
              className="w-20 bg-bg border border-line rounded px-2 py-1.5 text-[11px]"
            />
          </div>

          <div>
            <label className="block text-[10px] font-bold text-ink/40 uppercase mb-1">Feedback JSON</label>
            <input
              type="text"
              value={config.feedbackJson}
              onChange={e => setConfig(prev => ({ ...prev, feedbackJson: e.target.value }))}
              className="w-full bg-bg border border-line rounded px-2 py-1.5 text-[11px] font-mono"
            />
          </div>

          <div className="flex items-end gap-3">
            <label className="flex items-center gap-1.5 cursor-pointer">
              <input type="checkbox" checked={config.reportHtml} onChange={e => setConfig(prev => ({ ...prev, reportHtml: e.target.checked }))} />
              <span className="text-[10px]">HTML Report</span>
            </label>
            <label className="flex items-center gap-1.5 cursor-pointer">
              <input type="checkbox" checked={config.track} onChange={e => setConfig(prev => ({ ...prev, track: e.target.checked }))} />
              <span className="text-[10px]">Track</span>
            </label>
            <label className="flex items-center gap-1.5 cursor-pointer">
              <input type="checkbox" checked={config.judge} onChange={e => setConfig(prev => ({ ...prev, judge: e.target.checked }))} />
              <span className="text-[10px]">Judge</span>
            </label>
            <div>
              <label className="block text-[10px] font-bold text-ink/40 uppercase mb-1">Judge Model</label>
              <input
                type="text"
                value={config.judgeModel}
                onChange={e => setConfig(prev => ({ ...prev, judgeModel: e.target.value }))}
                placeholder={DEFAULT_JUDGE_MODEL}
                className="w-40 bg-bg border border-line rounded px-2 py-1.5 text-[11px] font-mono"
              />
            </div>
          </div>
        </div>
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
