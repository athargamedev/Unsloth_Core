import { useState, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { fetchJson } from '../api';
import type { DatasetContent } from '../api';
import { Card } from './Card';
import { Badge } from './Badge';

interface DatasetViewerProps {
  npcKey: string;
  technique: string;
}

export const DatasetViewer = ({ npcKey, technique }: DatasetViewerProps) => {
  const [data, setData] = useState<DatasetContent | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expandedIndex, setExpandedIndex] = useState<number | null>(null);
  const [sampleCount, setSampleCount] = useState(10);

  const fetchDataset = useCallback(async () => {
    if (!npcKey || !technique) return;
    setLoading(true);
    setError(null);
    try {
      const result = await fetchJson<DatasetContent>(
        `/api/dataset/${encodeURIComponent(npcKey)}/${encodeURIComponent(technique)}?n=${sampleCount}`
      );
      setData(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load dataset');
    } finally {
      setLoading(false);
    }
  }, [npcKey, technique, sampleCount]);

  useEffect(() => {
    fetchDataset();
  }, [fetchDataset]);

  const toggleExpand = (index: number) => {
    setExpandedIndex(expandedIndex === index ? null : index);
  };

  return (
    <Card title={`Dataset: ${npcKey}/${technique}`} subtitle={`Total entries: ${data?.total ?? '—'}`}>
      <div className="flex items-center gap-4 mb-4">
        <label className="text-[10px] font-bold text-ink/60">Samples:</label>
        <select
          value={sampleCount}
          onChange={(e) => setSampleCount(Number(e.target.value))}
          className="bg-bg border border-line text-[10px] rounded px-2 py-1"
        >
          <option value={5}>5</option>
          <option value={10}>10</option>
          <option value={25}>25</option>
          <option value={50}>50</option>
        </select>
        <button
          onClick={fetchDataset}
          className="text-[10px] text-accent underline font-mono ml-auto"
          disabled={loading}
        >
          {loading ? 'Loading...' : 'Refresh'}
        </button>
      </div>

      {error && (
        <div className="p-4 bg-warning/10 border border-warning/30 rounded text-[11px] text-warning mb-4">
          {error}
          <div className="mt-2">
            <span className="text-ink/60">Run </span>
            <code className="bg-bg px-1 py-0.5 rounded text-accent">./ucore generate {npcKey}</code>
            <span className="text-ink/60"> first to create a dataset.</span>
          </div>
        </div>
      )}

      {data && data.samples.length === 0 && !error && (
        <div className="p-4 bg-panel border border-line rounded text-[11px] text-ink/60 text-center">
          No samples found for this technique.
        </div>
      )}

      <div className="space-y-2 max-h-[500px] overflow-y-auto custom-scrollbar">
        <AnimatePresence>
          {data?.samples.map((sample, i) => (
            <motion.div
              key={i}
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              className="border border-line rounded overflow-hidden"
            >
              <button
                onClick={() => toggleExpand(i)}
                className="w-full flex items-center gap-2 px-3 py-2 bg-surface/50 hover:bg-surface text-left transition-colors"
              >
                <span className="text-[10px] font-mono text-ink/40 w-8 shrink-0">#{i + 1}</span>
                {sample._parseError ? (
                  <Badge variant="danger">Parse Error</Badge>
                ) : (
                  <Badge variant="default">
                    {(sample.messages?.length ?? 0)} turns
                  </Badge>
                )}
                <span className="text-[10px] text-ink/40 ml-auto">
                  {expandedIndex === i ? '▲' : '▼'}
                </span>
              </button>
              {expandedIndex === i && (
                <motion.div
                  initial={{ height: 0 }}
                  animate={{ height: 'auto' }}
                  exit={{ height: 0 }}
                  className="px-3 py-2 bg-bg border-t border-line"
                >
                  {sample._parseError ? (
                    <pre className="text-[10px] text-danger font-mono whitespace-pre-wrap break-all">
                      {sample._raw}
                    </pre>
                  ) : (
                    <div className="space-y-2">
                      {sample.messages?.map((msg, j) => (
                        <div key={j} className="text-[10px]">
                          <span className="font-bold text-accent uppercase tracking-wider">
                            {msg.role}
                          </span>
                          <span className="text-ink/80 ml-2">{msg.content}</span>
                        </div>
                      ))}
                      {/* Show non-message keys if no messages array */}
                      {!sample.messages && Object.entries(sample)
                        .filter(([k]) => !k.startsWith('_'))
                        .slice(0, 5)
                        .map(([k, v]) => (
                          <div key={k} className="text-[10px]">
                            <span className="font-bold text-accent">{k}:</span>
                            <span className="text-ink/80 ml-1">{String(v).slice(0, 200)}</span>
                          </div>
                        ))}
                    </div>
                  )}
                </motion.div>
              )}
            </motion.div>
          ))}
        </AnimatePresence>
      </div>

      {data && data.samples.length > 0 && (
        <div className="mt-3 text-[10px] text-ink/40 text-center">
          Showing {data.showing} of {data.total} samples
        </div>
      )}
    </Card>
  );
};
