import { useState, useEffect, useCallback } from 'react';
import { fetchJson, fetchOptionalJson } from '../api';
import type { FeedbackResult, FeedbackGapResult, ConceptFeedback } from '../api';

interface FeedbackFileInfo {
  name: string;
  path: string;
  lastModified: number;
}

export const FeedbackLoopPanel = () => {
  const [feedbackFiles, setFeedbackFiles] = useState<FeedbackFileInfo[]>([]);
  const [selectedFile, setSelectedFile] = useState<FeedbackFileInfo | null>(null);
  const [feedbackData, setFeedbackData] = useState<FeedbackResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [apiError, setApiError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [showConfig, setShowConfig] = useState(false);
  const [fbConfig, setFbConfig] = useState({
    dryRun: true,
    skipGapDetection: false,
    autoRetrain: false,
    trainPreset: 'fast-3b',
  });

  // Load feedback files
  const loadFiles = useCallback(async () => {
    try {
      const files = await fetchJson<FeedbackFileInfo[]>('/api/feedback-results');
      setFeedbackFiles(files);
      // Auto-select most recent
      if (files.length > 0 && !selectedFile) {
        setSelectedFile(files[0]);
      }
    } catch {
      // No feedback files yet
      setFeedbackFiles([]);
    }
  }, [selectedFile]);

  useEffect(() => {
    setLoading(true);
    loadFiles().finally(() => setLoading(false));
  }, []);

  // Load selected feedback content
  useEffect(() => {
    if (!selectedFile) {
      setFeedbackData(null);
      return;
    }
    setDetailLoading(true);
    setApiError(null);
    fetchOptionalJson<FeedbackResult>(`/api/feedback-result/file?path=${encodeURIComponent(selectedFile.path)}`)
      .then(data => {
        setFeedbackData(data);
      })
      .catch(err => setApiError(err instanceof Error ? err.message : 'Failed to load feedback'))
      .finally(() => setDetailLoading(false));
  }, [selectedFile]);

  const handleRunFeedback = async () => {
    if (!selectedFile) {
      setApiError('Select a feedback result first');
      return;
    }
    setRunning(true);
    setApiError(null);
    try {
      const payload: Record<string, unknown> = {
        commandId: 'feedback',
        type: 'Feedback',
        feedback_json: `eval/results/feedback/${selectedFile.name}`,
      };
      if (fbConfig.dryRun) payload['dry-run'] = true;
      if (fbConfig.skipGapDetection) payload['skip-gap-detection'] = true;
      if (fbConfig.autoRetrain) {
        payload['auto-retrain'] = true;
        payload['train-preset'] = fbConfig.trainPreset;
      }

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
          onClick={loadFiles}
          className="px-2 py-1 bg-line/20 text-ink/60 text-[10px] rounded hover:bg-line/40 transition-colors"
        >
          Refresh
        </button>
      </div>

      {apiError && (
        <div className="mx-4 mt-2 p-2 bg-danger/10 border border-danger/30 rounded text-[11px] text-danger">{apiError}</div>
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
                  <div className="mt-3 p-3 bg-surface border border-line rounded-sm space-y-3">
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-[11px]">
                      <label className="flex items-center gap-2 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={fbConfig.dryRun}
                          onChange={e => setFbConfig(prev => ({ ...prev, dryRun: e.target.checked }))}
                        />
                        <span>Dry Run</span>
                      </label>
                      <label className="flex items-center gap-2 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={fbConfig.skipGapDetection}
                          onChange={e => setFbConfig(prev => ({ ...prev, skipGapDetection: e.target.checked }))}
                        />
                        <span>Skip Gap Detection</span>
                      </label>
                      <label className="flex items-center gap-2 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={fbConfig.autoRetrain}
                          onChange={e => setFbConfig(prev => ({ ...prev, autoRetrain: e.target.checked }))}
                        />
                        <span>Auto-Retrain</span>
                      </label>
                      {fbConfig.autoRetrain && (
                        <div>
                          <label className="block text-[10px] text-ink/40 mb-1">Train Preset</label>
                          <select
                            value={fbConfig.trainPreset}
                            onChange={e => setFbConfig(prev => ({ ...prev, trainPreset: e.target.value }))}
                            className="bg-bg border border-line rounded px-2 py-1 text-[11px]"
                          >
                            <option value="smoke">Smoke</option>
                            <option value="fast-3b">Fast 3B</option>
                            <option value="quality">Quality</option>
                            <option value="safe-any">Safe Any</option>
                          </select>
                        </div>
                      )}
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
