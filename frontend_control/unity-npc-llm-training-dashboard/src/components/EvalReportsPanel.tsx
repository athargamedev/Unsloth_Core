import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { z } from 'zod';
import { fetchJson } from '../api';
import { Card } from './Card';
import { Badge } from './Badge';

// 1. Zod Schema Definition (The Blueprint)
// This strictly validates what the backend sends us so the frontend never crashes on bad data.
const EvalReportFileSchema = z.object({
  name: z.string(),
  path: z.string(),
});

const EvalReportGroupSchema = z.object({
  npcKey: z.string(),
  files: z.array(EvalReportFileSchema),
});

const EvalReportsDataSchema = z.object({
  reports: z.array(EvalReportGroupSchema),
  comparisons: z.array(EvalReportFileSchema),
});

// Infer TypeScript type directly from the schema (No need to write interfaces manually!)
type ValidatedEvalReportsData = z.infer<typeof EvalReportsDataSchema>;

export const EvalReportsPanel = () => {
  const [selectedNpc, setSelectedNpc] = useState<string | null>(null);

  // 2. React Query Usage
  // Automatically handles loading state, error catching, background refetching, and caching!
  const { data, isLoading: loading, error } = useQuery<ValidatedEvalReportsData, Error>({
    queryKey: ['eval-reports'],
    queryFn: async () => {
      const rawData = await fetchJson<unknown>('/api/eval-reports');
      // 3. Parse and Validate! Throws an error automatically if the data is malformed.
      return EvalReportsDataSchema.parse(rawData);
    },
  });

  const selectedGroup = data?.reports.find((r) => r.npcKey === selectedNpc) ?? null;

  return (
    <Card title="Evaluation Reports" subtitle={data ? `${data.reports.length} NPCs` : '—'}>
      {error && (
        <div className="p-3 bg-warning/10 border border-warning/30 rounded text-[11px] text-warning mb-4">
          {error.message}
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
        <div className="flex flex-col gap-4 lg:flex-row min-w-0">
          {/* NPC list */}
          <div className="w-full lg:w-56 shrink-0 space-y-1 min-w-0">
            {data.reports.length === 0 && !error && (
              <div className="text-[10px] text-ink/40 py-2">No reports available.</div>
            )}
            {data.reports.map((group) => (
              <button
                key={group.npcKey}
                onClick={() => setSelectedNpc(group.npcKey)}
                className={`w-full text-left px-3 py-2 text-[10px] font-mono rounded transition-colors min-w-0 ${
                  selectedNpc === group.npcKey
                    ? 'bg-accent/20 text-accent border border-accent/40'
                    : 'bg-surface border border-line hover:border-accent/30 text-ink/80'
                }`}
              >
                <span className="font-bold">{group.npcKey}</span>
                <Badge variant="default" className="ml-2">{group.files.length}</Badge>
                <div className="mt-1 text-[8px] text-ink/35 truncate">eval/reports/{group.npcKey}</div>
              </button>
            ))}
          </div>

          {/* File list */}
          <div className="flex-1 min-w-0 space-y-1">
            {!selectedNpc && (
              <div className="text-[10px] text-ink/40 py-4 text-center">
                Select an NPC to view reports
              </div>
            )}
            {selectedGroup && (
              <div className="px-3 py-2 rounded border border-line bg-bg/20 text-[9px] text-ink/45 font-mono break-all">
                Path: eval/reports/{selectedGroup.npcKey}
              </div>
            )}
            {selectedGroup?.files.map((file) => (
              <div
                key={file.name}
                className="flex flex-col gap-1 px-3 py-2 bg-surface border border-line rounded text-[10px] min-w-0"
              >
                <span className="font-mono text-ink/80 flex-1 truncate">{file.name}</span>
                <span className="text-[8px] text-ink/35 truncate">{file.path}</span>
                <a
                  href={`/api/eval-reports/file?path=${encodeURIComponent(file.path)}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-accent underline shrink-0 self-start"
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
        <div className="mt-4 pt-4 border-t border-line min-w-0">
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
