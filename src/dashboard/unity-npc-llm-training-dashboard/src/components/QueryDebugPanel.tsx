import { useEffect, useState, useCallback } from 'react';
import { useQueryClient } from '@tanstack/react-query';

interface QueryDebugInfo {
  total: number;
  stale: number;
  active: number;
  queries: Array<{
    key: string;
    state: string;
    dataAge: string;
    isStale: boolean;
    isFetching: boolean;
  }>;
}

/**
 * Development-only panel that shows React Query internal state.
 *
 * - Toggle visibility with **Ctrl+Shift+D**
 * - Displays total / stale / active queries
 * - Lists every cached query with its key, staleness, and fetch status
 *
 * Renders nothing in production (`import.meta.env.PROD`).
 */
export function QueryDebugPanel() {
  const queryClient = useQueryClient();
  const [visible, setVisible] = useState(false);

  // ── Keyboard shortcut: Ctrl+Shift+D ──
  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.ctrlKey && e.shiftKey && e.key === 'D') {
        e.preventDefault();
        setVisible((prev) => !prev);
      }
    },
    [],
  );

  useEffect(() => {
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [handleKeyDown]);

  // ── Gather debug info every 2 s while panel is open ──
  const [info, setInfo] = useState<QueryDebugInfo | null>(null);

  useEffect(() => {
    if (!visible) {
      setInfo(null);
      return;
    }

    function collect(): QueryDebugInfo {
      // Access internal query cache (protected but accessible).
      const cache = queryClient.getQueryCache();
      const all = cache.getAll();
      const now = Date.now();

      const queries = all.map((q) => {
        const state = q.state;
        const dataAge = state.dataUpdatedAt ? now - state.dataUpdatedAt : -1;
        return {
          key: JSON.stringify(q.queryKey),
          state: state.status,
          dataAge: dataAge >= 0 ? `${(dataAge / 1000).toFixed(0)}s` : 'never',
          isStale: state.isInvalidated || q.isStale(),
          isFetching: state.fetchStatus === 'fetching',
        };
      });

      return {
        total: queries.length,
        stale: queries.filter((q) => q.isStale).length,
        active: queries.filter((q) => q.isFetching).length,
        queries,
      };
    }

    setInfo(collect());
    const interval = setInterval(() => setInfo(collect()), 2000);
    return () => clearInterval(interval);
  }, [visible, queryClient]);

  // Panel only shows when toggled via Ctrl+Shift+D — no production gate needed.
  if (!visible) return null;

  return (
    <div className="fixed bottom-2 right-2 z-[9999] w-96 max-h-[60vh] overflow-y-auto bg-black/90 border border-white/20 rounded p-3 font-mono text-[11px] text-white shadow-2xl">
      <div className="flex justify-between items-center mb-2">
        <span className="font-bold text-accent uppercase tracking-wider text-[12px]">
          React Query Debug
        </span>
        <button
          onClick={() => setVisible(false)}
          className="text-white/40 hover:text-white transition-colors text-[14px] leading-none"
          title="Close (Ctrl+Shift+D)"
        >
          ✕
        </button>
      </div>

      {info && (
        <>
          <div className="flex gap-3 mb-2 text-[10px] text-white/60">
            <span>
              Total: <strong className="text-white">{info.total}</strong>
            </span>
            <span>
              Stale: <strong className="text-yellow-400">{info.stale}</strong>
            </span>
            <span>
              Fetching: <strong className="text-green-400">{info.active}</strong>
            </span>
          </div>

          <table className="w-full border-collapse">
            <thead>
              <tr className="text-[9px] text-white/40 uppercase tracking-wider">
                <th className="text-left pr-1">Query</th>
                <th className="text-center px-1">Status</th>
                <th className="text-center px-1">Age</th>
              </tr>
            </thead>
            <tbody>
              {info.queries.map((q) => (
                <tr key={q.key} className="border-t border-white/5 hover:bg-white/5">
                  <td className="py-1 pr-1 truncate max-w-[200px]" title={q.key}>
                    {q.key}
                  </td>
                  <td className="text-center px-1">
                    <span
                      className={
                        q.isFetching
                          ? 'text-green-400'
                          : q.isStale
                            ? 'text-yellow-400'
                            : 'text-white/40'
                      }
                    >
                      {q.isFetching ? 'fetch' : q.isStale ? 'stale' : q.state}
                    </span>
                  </td>
                  <td className="text-center px-1 text-white/40">{q.dataAge}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </div>
  );
}
