import { useState, useEffect, useRef, useCallback, useMemo, type KeyboardEvent } from 'react';
import { createPortal } from 'react-dom';
import { Search, ArrowUp, ArrowDown, X, Clock, Hash, Database, Cpu, Package, Play } from 'lucide-react';
import { motion, AnimatePresence } from 'motion/react';
import { cn } from '../lib/utils';
import { fetchJson } from '../api';
import { useAppStore } from '../stores/app-store';
import type { Subject, Dataset, RunArtifact, ExportArtifact, Job } from '../api';

interface SearchResult {
  id: string;
  label: string;
  sublabel?: string;
  category: 'NPC' | 'Dataset' | 'Run' | 'Export' | 'Job';
  tab: string;
  payload?: Record<string, string>;
}

const categoryIcons: Record<string, typeof Hash> = {
  NPC: Hash,
  Dataset: Database,
  Run: Cpu,
  Export: Package,
  Job: Play,
};

const categoryOrder = ['NPC', 'Dataset', 'Run', 'Export', 'Job'] as const;

export function GlobalSearch() {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [data, setData] = useState<{
    subjects: Subject[];
    datasets: Dataset[];
    runs: RunArtifact[];
    exports: ExportArtifact[];
    jobs: Job[];
  }>({
    subjects: [],
    datasets: [],
    runs: [],
    exports: [],
    jobs: [],
  });
  const [loading, setLoading] = useState(false);
  const [dataFetched, setDataFetched] = useState(false);

  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  const addRecentSearch = useAppStore((s) => s.addRecentSearch);
  const recentSearches = useAppStore((s) => s.recentSearches);
  const clearRecentSearches = useAppStore((s) => s.clearRecentSearches);

  // Fetch all searchable data when modal opens
  const fetchSearchData = useCallback(async () => {
    if (dataFetched) return;
    setLoading(true);
    try {
      const [subjects, datasets, runs, exports, jobs] = await Promise.all([
        fetchJson<Subject[]>('/api/subjects').catch(() => [] as Subject[]),
        fetchJson<Dataset[]>('/api/datasets').catch(() => [] as Dataset[]),
        fetchJson<RunArtifact[]>('/api/runs').catch(() => [] as RunArtifact[]),
        fetchJson<ExportArtifact[]>('/api/exports').catch(() => [] as ExportArtifact[]),
        fetchJson<{ jobs: Job[] }>('/api/jobs')
          .then((r) => r.jobs)
          .catch(() => [] as Job[]),
      ]);
      setData({ subjects, datasets, runs, exports, jobs });
      setDataFetched(true);
    } catch {
      // Data will be empty, that's fine
    } finally {
      setLoading(false);
    }
  }, [dataFetched]);

  // Open/close handlers via custom event
  useEffect(() => {
    const handleOpen = () => {
      setOpen(true);
      setDataFetched(false);
      setQuery('');
      setSelectedIndex(0);
    };
    window.addEventListener('open-search', handleOpen);
    return () => window.removeEventListener('open-search', handleOpen);
  }, []);

  // Focus input and fetch data when opened
  useEffect(() => {
    if (open) {
      inputRef.current?.focus();
      fetchSearchData();
    }
  }, [open, fetchSearchData]);

  // Reset selected index when query changes
  useEffect(() => {
    setSelectedIndex(0);
  }, [query]);

  // Build search results from all data
  const results = useMemo<SearchResult[]>(() => {
    if (!query.trim()) return [];
    const q = query.toLowerCase().trim();

    const all: SearchResult[] = [];

    // Subjects / NPCs
    for (const s of data.subjects) {
      if (s.id.toLowerCase().includes(q)) {
        all.push({
          id: `npc-${s.id}`,
          label: s.id,
          sublabel: s.path,
          category: 'NPC',
          tab: 'dataset_params',
          payload: { npcKey: s.id },
        });
      }
    }

    // Datasets
    for (const d of data.datasets) {
      if (d.id.toLowerCase().includes(q) || d.name.toLowerCase().includes(q)) {
        all.push({
          id: `ds-${d.id}`,
          label: d.name,
          sublabel: `${d.versions.length} version(s)`,
          category: 'Dataset',
          tab: 'datasets',
          payload: { npcKey: d.id, technique: d.versions[0]?.tag || '' },
        });
      }
    }

    // Runs
    for (const r of data.runs) {
      if (
        r.npcKey.toLowerCase().includes(q) ||
        r.id.toLowerCase().includes(q) ||
        (r.runId && r.runId.toLowerCase().includes(q))
      ) {
        all.push({
          id: `run-${r.id}`,
          label: `${r.npcKey} / ${r.runId ? r.runId.slice(0, 12) : r.id.slice(0, 12)}`,
          sublabel: r.model ? `model: ${r.model}` : undefined,
          category: 'Run',
          tab: 'analytics',
        });
      }
    }

    // Exports
    for (const e of data.exports) {
      if (e.npcKey.toLowerCase().includes(q) || e.file.toLowerCase().includes(q)) {
        all.push({
          id: `export-${e.npcKey}-${e.file}`,
          label: e.file,
          sublabel: e.npcKey,
          category: 'Export',
          tab: 'eval',
          payload: { npcKey: e.npcKey },
        });
      }
    }

    // Jobs
    for (const j of data.jobs) {
      if (
        j.name?.toLowerCase().includes(q) ||
        j.id.toLowerCase().includes(q) ||
        (j.npcKey && j.npcKey.toLowerCase().includes(q))
      ) {
        all.push({
          id: `job-${j.id}`,
          label: j.name || j.id.slice(0, 16),
          sublabel: `${j.type} · ${j.status}`,
          category: 'Job',
          tab: 'jobs',
          payload: { jobId: j.id },
        });
      }
    }

    return all;
  }, [query, data]);

  // Group results by category
  const groupedResults = useMemo(() => {
    const groups: Record<string, SearchResult[]> = {};
    for (const cat of categoryOrder) {
      const items = results.filter((r) => r.category === cat);
      if (items.length > 0) groups[cat] = items;
    }
    return groups;
  }, [results]);

  const flatResults = useMemo(() => {
    const flat: { result: SearchResult; isFirstInGroup: boolean }[] = [];
    for (const cat of categoryOrder) {
      const items = results.filter((r) => r.category === cat);
      items.forEach((r, i) => {
        flat.push({ result: r, isFirstInGroup: i === 0 });
      });
    }
    return flat;
  }, [results]);

  // Keyboard navigation
  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setOpen(false);
        return;
      }

      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setSelectedIndex((prev) => Math.min(prev + 1, flatResults.length - 1));
        // Scroll into view
        const el = listRef.current?.children[selectedIndex + 1] as HTMLElement | undefined;
        el?.scrollIntoView({ block: 'nearest' });
        return;
      }

      if (e.key === 'ArrowUp') {
        e.preventDefault();
        setSelectedIndex((prev) => Math.max(prev - 1, 0));
        const el = listRef.current?.children[selectedIndex - 1] as HTMLElement | undefined;
        el?.scrollIntoView({ block: 'nearest' });
        return;
      }

      if (e.key === 'Enter') {
        e.preventDefault();
        const selected = flatResults[selectedIndex];
        if (selected) {
          selectResult(selected.result);
        }
      }
    },
    [flatResults, selectedIndex],
  );

  const selectResult = useCallback(
    (result: SearchResult) => {
      addRecentSearch(result.label);
      window.dispatchEvent(
        new CustomEvent('navigate-tab', {
          detail: { tab: result.tab, ...result.payload },
        }),
      );
      setOpen(false);
    },
    [addRecentSearch],
  );

  const handleRecentClick = useCallback(
    (q: string) => {
      setQuery(q);
    },
    [],
  );

  return createPortal(
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.15 }}
          className="fixed inset-0 bg-black/60 z-[200] flex items-start justify-center pt-[15vh]"
          onClick={() => setOpen(false)}
        >
          <motion.div
            initial={{ opacity: 0, y: -12, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -12, scale: 0.97 }}
            transition={{ duration: 0.12 }}
            className="w-full max-w-lg bg-surface border border-line rounded-lg shadow-2xl shadow-black/50 overflow-hidden backdrop-blur-xl"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Search input */}
            <div className="flex items-center gap-3 px-4 py-3 border-b border-line">
              <Search className="w-4 h-4 text-ink/30 shrink-0" />
              <input
                ref={inputRef}
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Search NPCs, datasets, runs, exports, jobs…"
                className="flex-1 bg-transparent text-sm text-ink-bright placeholder:text-ink/30 outline-none font-mono"
              />
              <kbd className="hidden sm:inline-flex items-center px-1.5 py-0.5 text-[10px] font-mono text-ink/30 bg-line/30 rounded border border-line/50">
                <ArrowUp className="w-2.5 h-2.5 inline" />
                <ArrowDown className="w-2.5 h-2.5 inline" />
                <span className="mx-0.5">&</span>
                Enter
              </kbd>
              <button
                onClick={() => setOpen(false)}
                className="text-ink/30 hover:text-ink/60 transition-colors"
                aria-label="Close search"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Results */}
            <div
              ref={listRef}
              className="overflow-y-auto max-h-80 custom-scrollbar"
            >
              {loading && (
                <div className="flex items-center justify-center py-8">
                  <div className="w-4 h-4 border-2 border-accent border-t-transparent rounded-full animate-spin" />
                  <span className="ml-2 text-[12px] text-ink/40 font-mono">Searching…</span>
                </div>
              )}

              {!loading && query.trim() && flatResults.length === 0 && (
                <div className="flex flex-col items-center justify-center py-10 text-center">
                  <Search className="w-6 h-6 text-ink/20 mb-2" />
                  <span className="text-[12px] text-ink/30">
                    No results for &ldquo;{query}&rdquo;
                  </span>
                  <span className="text-[10px] text-ink/20 mt-1">
                    Try a different search term
                  </span>
                </div>
              )}

              {!loading && query.trim() && flatResults.length > 0 && (
                <>
                  {categoryOrder.map((cat) => {
                    const items = groupedResults[cat];
                    if (!items) return null;
                    const Icon = categoryIcons[cat];
                    return (
                      <div key={cat}>
                        <div className="flex items-center gap-2 px-4 py-1.5 bg-bg/40">
                          <Icon className="w-3 h-3 text-ink/30" />
                          <span className="text-[10px] font-bold text-ink/30 uppercase tracking-widest">
                            {cat}
                          </span>
                        </div>
                        {items.map((result) => {
                          const flatIdx = flatResults.findIndex(
                            (f) => f.result.id === result.id,
                          );
                          const isSelected = flatIdx === selectedIndex;
                          return (
                            <button
                              key={result.id}
                              onClick={() => selectResult(result)}
                              onMouseEnter={() => setSelectedIndex(flatIdx)}
                              className={cn(
                                'w-full flex items-center gap-3 px-4 py-2 text-left transition-colors',
                                isSelected
                                  ? 'bg-accent/10 text-ink-bright'
                                  : 'text-ink/70 hover:bg-white/[0.03]',
                              )}
                            >
                              <div
                                className={cn(
                                  'w-1.5 h-1.5 rounded-full shrink-0',
                                  isSelected ? 'bg-accent' : 'bg-ink/20',
                                )}
                              />
                              <div className="flex-1 min-w-0">
                                <div
                                  className={cn(
                                    'text-[12px] font-medium truncate',
                                    isSelected && 'text-ink-bright',
                                  )}
                                >
                                  {result.label}
                                </div>
                                {result.sublabel && (
                                  <div className="text-[10px] text-ink/40 truncate">
                                    {result.sublabel}
                                  </div>
                                )}
                              </div>
                              <span className="text-[9px] text-ink/20 uppercase tracking-wider shrink-0">
                                {result.category}
                              </span>
                            </button>
                          );
                        })}
                      </div>
                    );
                  })}
                </>
              )}

              {/* Recent searches */}
              {!query.trim() && recentSearches.length > 0 && (
                <div>
                  <div className="flex items-center justify-between px-4 py-1.5 bg-bg/40">
                    <div className="flex items-center gap-2">
                      <Clock className="w-3 h-3 text-ink/30" />
                      <span className="text-[10px] font-bold text-ink/30 uppercase tracking-widest">
                        Recent
                      </span>
                    </div>
                    <button
                      onClick={clearRecentSearches}
                      className="text-[10px] text-ink/20 hover:text-ink/40 transition-colors"
                    >
                      Clear
                    </button>
                  </div>
                  {recentSearches.map((q) => (
                    <button
                      key={q}
                      onClick={() => handleRecentClick(q)}
                      className="w-full flex items-center gap-3 px-4 py-2 text-left text-ink/60 hover:bg-white/[0.03] transition-colors"
                    >
                      <Clock className="w-3 h-3 text-ink/20 shrink-0" />
                      <span className="text-[12px] truncate">{q}</span>
                    </button>
                  ))}
                </div>
              )}

              {!query.trim() && recentSearches.length === 0 && (
                <div className="flex flex-col items-center justify-center py-10 text-center">
                  <Search className="w-6 h-6 text-ink/20 mb-2" />
                  <span className="text-[12px] text-ink/30">Press Ctrl+K to search</span>
                  <span className="text-[10px] text-ink/20 mt-1">
                    Search across NPCs, datasets, runs, exports, and jobs
                  </span>
                  <div className="flex gap-2 mt-3">
                    {(['NPC', 'Dataset', 'Run', 'Export', 'Job'] as const).map((cat) => {
                      const Icon = categoryIcons[cat];
                      return (
                        <span
                          key={cat}
                          className="flex items-center gap-1 px-2 py-0.5 bg-line/20 rounded text-[10px] text-ink/30"
                        >
                          <Icon className="w-2.5 h-2.5" />
                          {cat}
                        </span>
                      );
                    })}
                  </div>
                </div>
              )}
            </div>

            {/* Footer hint */}
            <div className="px-4 py-2 border-t border-line bg-bg/40 flex items-center gap-3 text-[10px] text-ink/20">
              <span>
                <kbd className="px-1 py-0.5 bg-line/30 rounded border border-line/50 text-[9px] font-mono">
                  ↑
                </kbd>
                <kbd className="px-1 py-0.5 bg-line/30 rounded border border-line/50 text-[9px] font-mono ml-0.5">
                  ↓
                </kbd>{' '}
                navigate
              </span>
              <span>
                <kbd className="px-1 py-0.5 bg-line/30 rounded border border-line/50 text-[9px] font-mono">
                  ↵
                </kbd>{' '}
                select
              </span>
              <span>
                <kbd className="px-1 py-0.5 bg-line/30 rounded border border-line/50 text-[9px] font-mono">
                  Esc
                </kbd>{' '}
                close
              </span>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>,
    document.body,
  );
}
