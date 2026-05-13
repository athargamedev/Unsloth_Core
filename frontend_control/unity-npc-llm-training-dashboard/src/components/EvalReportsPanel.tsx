import { useState, useEffect } from 'react';
import { fetchJson } from '../api';
import type { EvalReportsData } from '../api';
import { Card } from './Card';
import { Badge } from './Badge';

export const EvalReportsPanel = () => {
  const [data, setData] = useState<EvalReportsData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedNpc, setSelectedNpc] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    fetchJson<EvalReportsData>('/api/eval-reports')
      .then(setData)
      .catch((err) => setError(err instanceof Error ? err.message : 'Failed to load eval reports'))
      .finally(() => setLoading(false));
  }, []);

  const selectedGroup = data?.reports.find((r) => r.npcKey === selectedNpc) ?? null;

  return (
    <Card title="Evaluation Reports" subtitle={data ? `${data.reports.length} NPCs` : '—'}>
      {error && (
        <div className="p-3 bg-warning/10 border border-warning/30 rounded text-[11px] text-warning mb-4">
          {error}
          <div className="mt-2 text-ink/60">
            No evaluation reports yet.{' '}
            <span className="text-accent">Run an evaluation to generate reports.</span>
          </div>
        </div>
      )}

      {loading && (
        <div className="text-[10px] text-ink/40 py-4 text-center">Loading reports...</div>
      )}

      {data && !loading && (
        <div className="flex gap-4">
          {/* NPC list */}
          <div className="w-48 shrink-0 space-y-1">
            {data.reports.length === 0 && !error && (
              <div className="text-[10px] text-ink/40 py-2">No reports available.</div>
            )}
            {data.reports.map((group) => (
              <button
                key={group.npcKey}
                onClick={() => setSelectedNpc(group.npcKey)}
                className={`w-full text-left px-3 py-2 text-[10px] font-mono rounded transition-colors ${
                  selectedNpc === group.npcKey
                    ? 'bg-accent/20 text-accent border border-accent/40'
                    : 'bg-surface border border-line hover:border-accent/30 text-ink/80'
                }`}
              >
                <span className="font-bold">{group.npcKey}</span>
                <Badge variant="default" className="ml-2">{group.files.length}</Badge>
              </button>
            ))}
          </div>

          {/* File list */}
          <div className="flex-1 space-y-1">
            {!selectedNpc && (
              <div className="text-[10px] text-ink/40 py-4 text-center">
                Select an NPC to view reports
              </div>
            )}
            {selectedGroup?.files.map((file) => (
              <div
                key={file.name}
                className="flex items-center gap-3 px-3 py-2 bg-surface border border-line rounded text-[10px]"
              >
                <span className="font-mono text-ink/80 flex-1 truncate">{file.name}</span>
                <a
                  href={`/api/eval-reports/file?path=${encodeURIComponent(file.path)}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-accent underline shrink-0"
                  title="Opens in a new tab (external to dashboard)"
                >
                  View
                </a>
              </div>
            ))}
          </div>
        </div>
      )}

      {data && data.comparisons.length > 0 && (
        <div className="mt-4 pt-4 border-t border-line">
          <h4 className="text-[10px] font-bold text-ink/40 uppercase tracking-widest mb-2">Comparisons</h4>
          <div className="space-y-1">
            {data.comparisons.map((comp) => (
              <div key={comp.name} className="flex items-center gap-3 px-3 py-2 bg-surface border border-line rounded text-[10px]">
                <span className="font-mono text-ink/80 flex-1 truncate">{comp.name}</span>
                <span className="text-ink/35 shrink-0" title="Only eval/reports files are served by the safe report viewer.">Not served</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </Card>
  );
};
