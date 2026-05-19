import { useEffect, useMemo, useState } from 'react';
import { motion } from 'motion/react';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  AreaChart,
  Area,
  Legend,
} from 'recharts';
import { RefreshCw, CheckCircle2, AlertTriangle, Layers3, Gauge, Database, Sparkles, Target } from 'lucide-react';
import { Card } from './Card';
import { cn } from '../lib/utils';
import { fetchJson, type Job, type RunArtifact, type TensorBoardData } from '../api';

interface TensorBoardPanelProps {
  jobs: Job[];
  runs: RunArtifact[];
  onRefresh: () => void;
  isLive?: boolean;
}

type QualitySummary = {
  npc_key: string;
  technique: string;
  total: number;
  passed: number;
  failed: number;
  pass_rate: number;
  metrics?: Record<string, { average_score?: number; pass_rate?: number; count?: number }>;
  categories?: Record<string, { total?: number; passed?: number; pass_rate?: number }>;
};

type CurvePoint = { step: number; value: number };

type RunProfile = RunArtifact & {
  key: string;
  shortModel: string;
  shortDataset: string;
  statusLabel: string;
  quality?: QualitySummary | null;
  curve?: TensorBoardData | null;
  tbError?: string | null;
  lossSeries: CurvePoint[];
  lrSeries: CurvePoint[];
  finalLoss: number | null;
  bestLoss: number | null;
  firstLoss: number | null;
  lossDelta: number | null;
  steps: number;
  readyScore: number;
  decision: string;
};

const COLORS = ['#5eead4', '#60a5fa', '#f472b6', '#f59e0b'];

const shortText = (value?: string | null, fallback = '--') => {
  if (!value) return fallback;
  const trimmed = value.trim();
  return trimmed.length > 42 ? `…${trimmed.slice(-39)}` : trimmed;
};

const modelTail = (value?: string | null) => {
  if (!value) return '--';
  const parts = value.split('/');
  return parts[parts.length - 1] || value;
};

const datasetTail = (value?: string | null) => {
  if (!value) return '--';
  const parts = value.split('/');
  return parts.slice(-3).join('/');
};

const parseTechnique = (run: RunArtifact) => run.technique || run.datasetPath?.split('/').at(-2) || '--';

const runKey = (run: RunArtifact) => `${run.npcKey}/${run.runId || run.id}`;

const pickSeries = (tb: TensorBoardData | null | undefined, tags: string[]) => {
  if (!tb?.scalars) return [] as CurvePoint[];
  for (const tag of tags) {
    const series = tb.scalars[tag];
    if (Array.isArray(series) && series.length > 0) return series.map((point) => ({ step: point.step, value: point.value }));
  }
  return [] as CurvePoint[];
};

const buildStatusLabel = (run: RunArtifact) => {
  if (run.hasTensorBoard) return 'TensorBoard ready';
  if (run.hasAdapter) return 'Adapter saved';
  if (run.hasConfigSnapshot) return 'Config captured';
  return 'Metadata only';
};

const mergeCurves = (profiles: RunProfile[], seriesKey: 'lossSeries' | 'lrSeries') => {
  const stepMap = new Map<number, Record<string, number | string>>();
  profiles.forEach((profile, index) => {
    const points = profile[seriesKey];
    const key = profile.key;
    for (const point of points) {
      const row = stepMap.get(point.step) || { step: point.step };
      row[key] = point.value;
      stepMap.set(point.step, row);
    }
    if (!stepMap.size && index === profiles.length - 1) {
      stepMap.set(1, { step: 1 });
    }
  });
  return Array.from(stepMap.values()).sort((a, b) => Number(a.step) - Number(b.step));
};

const metric = (value: number | null | undefined, digits = 4) => (value === null || value === undefined || Number.isNaN(value) ? '--' : value.toFixed(digits));

const EmptyState = ({ title, subtitle }: { title: string; subtitle: string }) => (
  <div className="flex-1 flex items-center justify-center rounded border border-dashed border-line/60 bg-surface/20 p-8 text-center">
    <div>
      <p className="text-xs font-bold uppercase tracking-widest text-ink-bright">{title}</p>
      <p className="mt-2 text-[11px] text-ink/45 max-w-md">{subtitle}</p>
    </div>
  </div>
);

export const TensorBoardPanel = ({ jobs, runs, onRefresh, isLive }: TensorBoardPanelProps) => {
  const [search, setSearch] = useState('');
  const [npcFilter, setNpcFilter] = useState('all');
  const [techniqueFilter, setTechniqueFilter] = useState('all');
  const [modelFilter, setModelFilter] = useState('all');
  const [primaryRunId, setPrimaryRunId] = useState('');
  const [compareRunIds, setCompareRunIds] = useState<string[]>([]);
  const [curveCache, setCurveCache] = useState<Record<string, TensorBoardData | null>>({});
  const [qualityCache, setQualityCache] = useState<Record<string, QualitySummary | null>>({});
  const [loadingCache, setLoadingCache] = useState<Record<string, boolean>>({});
  const [refreshTick, setRefreshTick] = useState(0);

  const normalizedRuns = useMemo(() => runs
    .slice()
    .sort((a, b) => (b.updatedAt || '').localeCompare(a.updatedAt || '')),
  [runs]);

  const availableNpcs = useMemo(() => Array.from(new Set(normalizedRuns.map((run) => run.npcKey))).sort(), [normalizedRuns]);
  const availableTechniques = useMemo(() => Array.from(new Set(normalizedRuns.map((run) => parseTechnique(run)).filter(Boolean))).sort(), [normalizedRuns]);
  const availableModels = useMemo(() => Array.from(new Set(normalizedRuns.map((run) => modelTail(run.model)).filter(Boolean))).sort(), [normalizedRuns]);

  const filteredRuns = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return normalizedRuns.filter((run) => {
      const tech = parseTechnique(run);
      const model = modelTail(run.model);
      const fields = [run.runId, run.npcKey, run.model || '', run.datasetPath || '', tech, run.path || ''].join(' ').toLowerCase();
      if (npcFilter !== 'all' && run.npcKey !== npcFilter) return false;
      if (techniqueFilter !== 'all' && tech !== techniqueFilter) return false;
      if (modelFilter !== 'all' && model !== modelFilter) return false;
      if (needle && !fields.includes(needle)) return false;
      return true;
    });
  }, [normalizedRuns, search, npcFilter, techniqueFilter, modelFilter]);

  useEffect(() => {
    if (filteredRuns.length === 0) {
      setPrimaryRunId('');
      setCompareRunIds([]);
      return;
    }
    if (!filteredRuns.some((run) => runKey(run) === primaryRunId)) {
      setPrimaryRunId(runKey(filteredRuns[0]));
    }
    setCompareRunIds((current) => {
      const valid = current.filter((id) => filteredRuns.some((run) => runKey(run) === id) && id !== primaryRunId);
      if (valid.length > 0) return valid.slice(0, 3);
      if (filteredRuns.length > 1) return [runKey(filteredRuns[1])];
      return [];
    });
  }, [filteredRuns, primaryRunId]);

  const selectedRuns = useMemo(() => {
    const picks = [primaryRunId, ...compareRunIds].filter(Boolean);
    const seen = new Set<string>();
    return picks
      .map((id) => filteredRuns.find((run) => runKey(run) === id) || normalizedRuns.find((run) => runKey(run) === id))
      .filter((run): run is RunArtifact => Boolean(run) && !seen.has(runKey(run)) && Boolean(seen.add(runKey(run))));
  }, [primaryRunId, compareRunIds, filteredRuns, normalizedRuns]);

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      const targets = selectedRuns.filter((run) => {
        const key = runKey(run);
        const hasCurve = Object.prototype.hasOwnProperty.call(curveCache, key);
        const hasQuality = Object.prototype.hasOwnProperty.call(qualityCache, key);
        return !hasCurve || !hasQuality;
      });
      if (targets.length === 0) return;

      await Promise.all(targets.map(async (run) => {
        const key = runKey(run);
        setLoadingCache((current) => ({ ...current, [key]: true }));
        try {
          const tbPromise = fetchJson<TensorBoardData>(`/api/tensorboard?npcKey=${encodeURIComponent(run.npcKey)}&runId=${encodeURIComponent(run.runId || run.id)}`);
          const technique = parseTechnique(run);
          const qualityPromise = technique && technique !== '--'
            ? fetchJson<QualitySummary>(`/api/datasets/quality-summary/${encodeURIComponent(run.npcKey)}/${encodeURIComponent(technique)}`)
            : Promise.reject(new Error('missing technique'));
          const [tbData, qualityData] = await Promise.allSettled([tbPromise, qualityPromise]);
          if (cancelled) return;
          setCurveCache((current) => ({
            ...current,
            [key]: tbData.status === 'fulfilled' ? tbData.value : null,
          }));
          setQualityCache((current) => ({
            ...current,
            [key]: qualityData.status === 'fulfilled' ? qualityData.value : null,
          }));
        } catch {
          if (!cancelled) {
            setCurveCache((current) => ({ ...current, [key]: null }));
          }
        } finally {
          if (!cancelled) {
            setLoadingCache((current) => ({ ...current, [key]: false }));
          }
        }
      }));
    };

    load();
    return () => { cancelled = true; };
  }, [selectedRuns, refreshTick]);

  const profiles = useMemo<RunProfile[]>(() => selectedRuns.map((run) => {
    const key = runKey(run);
    const curve = curveCache[key] || null;
    const quality = qualityCache[key] || null;
    const lossSeries = pickSeries(curve, ['train/loss', 'loss']);
    const lrSeries = pickSeries(curve, ['train/learning_rate', 'learning_rate']);
    const finalLoss = lossSeries.length ? lossSeries[lossSeries.length - 1].value : (run.loss ?? null);
    const bestLoss = lossSeries.length ? Math.min(...lossSeries.map((point) => point.value)) : (run.loss ?? null);
    const firstLoss = lossSeries.length ? lossSeries[0].value : null;
    const lossDelta = firstLoss !== null && finalLoss !== null ? finalLoss - firstLoss : null;
    const steps = Math.max(lossSeries.length, lrSeries.length, 0);
    const readyScore = [run.hasConfigSnapshot, run.hasTensorBoard, run.hasAdapter, Boolean(quality?.pass_rate && quality.pass_rate >= 0.7)].filter(Boolean).length;
    const decision = !run.hasTensorBoard
      ? 'No TensorBoard data yet'
      : quality && quality.pass_rate < 0.7
        ? 'Fix dataset quality before retraining'
        : lossDelta !== null && lossDelta < 0
          ? 'Promising: loss is still improving'
          : 'Stable: review against baseline before export';

    return {
      ...run,
      key,
      shortModel: modelTail(run.model),
      shortDataset: datasetTail(run.datasetPath),
      statusLabel: buildStatusLabel(run),
      quality,
      curve,
      tbError: curve?.error || null,
      lossSeries,
      lrSeries,
      finalLoss,
      bestLoss,
      firstLoss,
      lossDelta,
      steps,
      readyScore,
      decision,
    };
  }), [selectedRuns, curveCache, qualityCache]);

  const primary = profiles[0] || null;
  const secondary = profiles.slice(1);
  const lossChart = mergeCurves(profiles, 'lossSeries');
  const lrChart = mergeCurves(profiles, 'lrSeries');
  const hasLossData = profiles.some((profile) => profile.lossSeries.length > 0);
  const hasLrData = profiles.some((profile) => profile.lrSeries.length > 0);

  const selectedJobs = useMemo(() => {
    const jobMap = new Map<string, Job>();
    jobs.forEach((job) => {
      if (job.id) jobMap.set(job.id, job);
      if (job.npcKey) jobMap.set(job.npcKey, job);
    });
    return jobMap;
  }, [jobs]);

  const linkedJob = primary ? selectedJobs.get(primary.npcKey) || null : null;
  const compareCount = selectedRuns.length;

  const addCompareRun = (id: string) => {
    setCompareRunIds((current) => {
      if (current.includes(id) || id === primaryRunId) return current;
      return [...current, id].slice(0, 3);
    });
  };

  const removeCompareRun = (id: string) => setCompareRunIds((current) => current.filter((item) => item !== id));

  const toggleCompareRun = (id: string) => {
    setCompareRunIds((current) => current.includes(id) ? current.filter((item) => item !== id) : [...current, id].slice(0, 3));
  };

  const togglePrimary = (id: string) => {
    setPrimaryRunId(id);
    setCompareRunIds((current) => current.filter((item) => item !== id));
  };

  const qualityLabel = (quality?: QualitySummary | null) => {
    if (!quality) return 'No gate';
    if (quality.pass_rate >= 0.8) return 'Pass';
    if (quality.pass_rate >= 0.6) return 'Review';
    return 'Fail';
  };

  const summaryTiles = primary
    ? [
        { label: 'Final loss', value: metric(primary.finalLoss), icon: Gauge },
        { label: 'Best loss', value: metric(primary.bestLoss), icon: Target },
        { label: 'TB steps', value: String(primary.steps || 0), icon: Layers3 },
        { label: 'Dataset gate', value: primary.quality ? `${Math.round(primary.quality.pass_rate * 100)}%` : '--', icon: Database },
      ]
    : [];

  return (
    <motion.div
      key="analytics"
      initial={{ opacity: 0, scale: 0.98 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.98 }}
      className="flex-1 overflow-hidden p-4 flex flex-col gap-4"
    >
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h3 className="text-xs font-bold text-ink-bright uppercase tracking-widest">TensorBoard Decision Studio</h3>
          <p className="mt-1 text-[11px] text-ink/45 max-w-3xl">
            Compare runs by model, dataset, technique, and quality gate. The selected curve is the current decision target.
          </p>
        </div>
        <div className="flex items-center gap-3 text-[10px] font-mono uppercase tracking-wider">
          {isLive && (
            <span className="flex items-center gap-1 text-success font-bold">
              <span className="w-1.5 h-1.5 rounded-full bg-success animate-pulse" /> Live
            </span>
          )}
          <button onClick={() => { setCurveCache({}); setQualityCache({}); setRefreshTick((value) => value + 1); onRefresh(); }} className="inline-flex items-center gap-2 px-3 py-1.5 rounded border border-line bg-panel text-ink/70 hover:text-ink-bright hover:bg-white/5 transition-colors">
            <RefreshCw className="w-3 h-3" /> Refresh workspace
          </button>
        </div>
      </div>

      <div className="grid grid-cols-12 gap-4 flex-1 overflow-hidden">
        <Card className="col-span-12 xl:col-span-4 flex flex-col overflow-hidden" title="Run Library" subtitle={`${filteredRuns.length} runs`}>
          <div className="space-y-3">
            <div className="grid grid-cols-2 gap-2">
              <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search run / dataset / model" className="col-span-2 rounded border border-line bg-bg/50 px-3 py-2 text-[11px] font-mono text-ink-bright outline-none focus:border-accent" />
              <select value={npcFilter} onChange={(e) => setNpcFilter(e.target.value)} className="rounded border border-line bg-bg/50 px-2 py-2 text-[11px] font-mono text-ink-bright outline-none">
                <option value="all">All NPCs</option>
                {availableNpcs.map((npc) => <option key={npc} value={npc}>{npc}</option>)}
              </select>
              <select value={techniqueFilter} onChange={(e) => setTechniqueFilter(e.target.value)} className="rounded border border-line bg-bg/50 px-2 py-2 text-[11px] font-mono text-ink-bright outline-none">
                <option value="all">All techniques</option>
                {availableTechniques.map((technique) => <option key={technique} value={technique}>{technique}</option>)}
              </select>
              <select value={modelFilter} onChange={(e) => setModelFilter(e.target.value)} className="col-span-2 rounded border border-line bg-bg/50 px-2 py-2 text-[11px] font-mono text-ink-bright outline-none">
                <option value="all">All models</option>
                {availableModels.map((model) => <option key={model} value={model}>{model}</option>)}
              </select>
            </div>

            <div className="max-h-[26rem] overflow-auto custom-scrollbar rounded border border-line/50 bg-bg/20">
              {filteredRuns.length === 0 ? (
                <EmptyState title="No runs match the filters" subtitle="Try widening the NPC, technique, or model filters." />
              ) : (
                <table className="w-full text-left text-[10px] font-mono">
                  <thead className="sticky top-0 bg-header/90 backdrop-blur-sm text-ink/45 uppercase tracking-widest">
                    <tr>
                      <th className="p-2 w-8"></th>
                      <th className="p-2">Run</th>
                      <th className="p-2 text-right">Loss</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-line/20">
                    {filteredRuns.map((run) => {
                      const key = runKey(run);
                      const isPrimary = key === primaryRunId;
                      const isCompared = compareRunIds.includes(key);
                      const quality = qualityCache[key];
                      return (
                        <tr key={key} className={cn('hover:bg-accent/10 transition-colors cursor-pointer', isPrimary && 'bg-accent/20', isCompared && 'bg-accent/10')} onClick={() => togglePrimary(key)}>
                          <td className="p-2 align-top">
                            <button
                              onClick={(e) => { e.stopPropagation(); toggleCompareRun(key); }}
                              className={cn('w-4 h-4 rounded border flex items-center justify-center', isCompared ? 'bg-accent border-accent' : 'border-line')}
                              title="Compare this run"
                            >
                              {isCompared && <span className="w-1.5 h-1.5 rounded-full bg-bg" />}
                            </button>
                          </td>
                          <td className="p-2 align-top">
                            <div className="space-y-1">
                              <div className="flex items-center gap-2">
                                <span className="font-bold text-ink-bright">{run.npcKey}</span>
                                {isPrimary && <span className="px-1.5 py-0.5 rounded bg-accent/20 text-accent text-[9px] uppercase font-bold">Primary</span>}
                                {loadingCache[key] && <span className="text-[9px] text-ink/35">Loading…</span>}
                              </div>
                              <div className="text-ink/55 truncate">{shortText(run.runId)}</div>
                              <div className="text-ink/35 truncate">{shortText(run.model || '')}</div>
                              <div className="flex flex-wrap gap-1 pt-1 text-[9px] uppercase tracking-widest">
                                <span className="px-1.5 py-0.5 rounded border border-line/40 text-ink/50">{parseTechnique(run)}</span>
                                <span className="px-1.5 py-0.5 rounded border border-line/40 text-ink/50">{qualityLabel(quality)}</span>
                                <span className="px-1.5 py-0.5 rounded border border-line/40 text-ink/50">{buildStatusLabel(run)}</span>
                              </div>
                            </div>
                          </td>
                          <td className="p-2 text-right align-top">
                            <div className="font-bold text-ink-bright">{metric(run.loss, 4)}</div>
                            <div className="text-[9px] text-ink/35">{run.hasTensorBoard ? 'TB' : 'logs'}</div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              )}
            </div>
          </div>
        </Card>

        <div className="col-span-12 xl:col-span-8 flex flex-col gap-4 overflow-hidden">
          <Card className="flex-1 overflow-hidden" title="Selected Run" subtitle={primary ? `${primary.npcKey} · ${primary.runId}` : 'Choose a run'}>
            {!primary ? (
              <EmptyState title="No run selected" subtitle="Pick a run on the left to inspect its curve, dataset gate, and training configuration." />
            ) : (
              <div className="flex flex-col gap-4 h-full overflow-hidden">
                <div className="grid grid-cols-2 xl:grid-cols-4 gap-3">
                  {summaryTiles.map((tile) => {
                    const Icon = tile.icon;
                    return (
                      <div key={tile.label} className="rounded border border-line/60 bg-bg/30 p-3">
                        <div className="flex items-center justify-between gap-2 text-[9px] uppercase tracking-widest text-ink/40">
                          <span>{tile.label}</span>
                          <Icon className="w-3 h-3 text-accent" />
                        </div>
                        <div className="mt-2 text-sm font-bold text-ink-bright">{tile.value}</div>
                      </div>
                    );
                  })}
                </div>

                <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
                  <div className="xl:col-span-2 space-y-4">
                    <div className="rounded border border-line/60 bg-bg/20 p-3">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <div className="space-y-1">
                          <div className="text-[10px] uppercase tracking-widest text-ink/40">Scope</div>
                          <div className="flex flex-wrap gap-2 text-[10px] font-mono">
                            <span className="px-2 py-1 rounded bg-accent/15 text-accent border border-accent/30">Model: {modelTail(primary.model)}</span>
                            <span className="px-2 py-1 rounded bg-panel border border-line text-ink/70">Dataset: {datasetTail(primary.datasetPath)}</span>
                            <span className="px-2 py-1 rounded bg-panel border border-line text-ink/70">Technique: {parseTechnique(primary)}</span>
                          </div>
                        </div>
                        <div className="flex items-center gap-2 text-[10px] uppercase tracking-widest">
                          <span className={cn('px-2 py-1 rounded border', primary.quality ? (primary.quality.pass_rate >= 0.8 ? 'border-success/30 text-success bg-success/10' : primary.quality.pass_rate >= 0.6 ? 'border-warning/30 text-warning bg-warning/10' : 'border-danger/30 text-danger bg-danger/10') : 'border-line text-ink/50 bg-panel')}>
                            {primary.quality ? `Quality ${Math.round(primary.quality.pass_rate * 100)}%` : 'Quality unavailable'}
                          </span>
                          <span className="px-2 py-1 rounded border border-line text-ink/50 bg-panel">Ready score {primary.readyScore}/4</span>
                        </div>
                      </div>
                    </div>

                    <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
                      <div className="rounded border border-line/60 bg-bg/20 p-3">
                        <div className="mb-2 text-[10px] uppercase tracking-widest text-ink/40">Loss curve</div>
                        {!hasLossData ? (
                          <EmptyState title="No loss curve" subtitle={primary.tbError || 'TensorBoard data is missing for this run.'} />
                        ) : (
                          <div className="h-56">
                            <ResponsiveContainer width="100%" height="100%">
                              <LineChart data={lossChart}>
                                <CartesianGrid strokeDasharray="3 3" stroke="var(--line)" opacity={0.25} />
                                <XAxis dataKey="step" stroke="var(--ink)" fontSize={9} opacity={0.45} />
                                <YAxis stroke="var(--ink)" fontSize={9} opacity={0.45} />
                                <Tooltip contentStyle={{ background: 'var(--header)', border: '1px solid var(--line)', borderRadius: 6, fontSize: 10 }} />
                                <Legend />
                                {profiles.map((profile, index) => (
                                  <Line
                                    key={profile.key}
                                    type="monotone"
                                    dataKey={profile.key}
                                    stroke={COLORS[index % COLORS.length]}
                                    strokeWidth={profile.key === primary.key ? 3 : 2}
                                    dot={false}
                                    name={`${profile.npcKey} · ${profile.shortModel}`}
                                    connectNulls
                                  />
                                ))}
                              </LineChart>
                            </ResponsiveContainer>
                          </div>
                        )}
                      </div>

                      <div className="rounded border border-line/60 bg-bg/20 p-3">
                        <div className="mb-2 text-[10px] uppercase tracking-widest text-ink/40">Learning rate</div>
                        {!hasLrData ? (
                          <EmptyState title="No learning-rate curve" subtitle="Learning-rate scalars were not found in the TensorBoard logs." />
                        ) : (
                          <div className="h-56">
                            <ResponsiveContainer width="100%" height="100%">
                              <AreaChart data={lrChart}>
                                <CartesianGrid strokeDasharray="3 3" stroke="var(--line)" opacity={0.25} />
                                <XAxis dataKey="step" stroke="var(--ink)" fontSize={9} opacity={0.45} />
                                <YAxis stroke="var(--ink)" fontSize={9} opacity={0.45} />
                                <Tooltip contentStyle={{ background: 'var(--header)', border: '1px solid var(--line)', borderRadius: 6, fontSize: 10 }} />
                                <Legend />
                                {profiles.map((profile, index) => (
                                  <Area
                                    key={profile.key}
                                    type="monotone"
                                    dataKey={profile.key}
                                    stroke={COLORS[index % COLORS.length]}
                                    fill={COLORS[index % COLORS.length]}
                                    fillOpacity={0.12}
                                    name={`${profile.npcKey} · ${profile.shortModel}`}
                                    connectNulls
                                  />
                                ))}
                              </AreaChart>
                            </ResponsiveContainer>
                          </div>
                        )}
                      </div>
                    </div>
                  </div>

                  <div className="space-y-4">
                    <div className="rounded border border-line/60 bg-bg/20 p-3">
                      <div className="flex items-center justify-between mb-3">
                        <div className="text-[10px] uppercase tracking-widest text-ink/40">Decision summary</div>
                        <Sparkles className="w-3.5 h-3.5 text-accent" />
                      </div>
                      <div className="text-sm font-bold text-ink-bright">{primary.decision}</div>
                      <div className="mt-2 text-[11px] text-ink/50 space-y-1">
                        <div>Training loss: {metric(primary.finalLoss)} → {metric(primary.bestLoss)}</div>
                        <div>Dataset gate: {primary.quality ? `${primary.quality.passed}/${primary.quality.total} passed` : 'not loaded'}</div>
                        <div>TensorBoard: {primary.tbError ? primary.tbError : 'available'}</div>
                      </div>
                    </div>

                    <div className="rounded border border-line/60 bg-bg/20 p-3">
                      <div className="flex items-center justify-between mb-3">
                        <div className="text-[10px] uppercase tracking-widest text-ink/40">Configuration</div>
                        <CheckCircle2 className="w-3.5 h-3.5 text-success" />
                      </div>
                      <div className="space-y-2 text-[11px]">
                        <div className="flex justify-between gap-2"><span className="text-ink/45">Model</span><span className="text-ink-bright text-right">{modelTail(primary.model)}</span></div>
                        <div className="flex justify-between gap-2"><span className="text-ink/45">Dataset</span><span className="text-ink-bright text-right">{datasetTail(primary.datasetPath)}</span></div>
                        <div className="flex justify-between gap-2"><span className="text-ink/45">Technique</span><span className="text-ink-bright text-right">{parseTechnique(primary)}</span></div>
                        <div className="flex justify-between gap-2"><span className="text-ink/45">LoRA</span><span className="text-ink-bright text-right">r {primary.loraRank ?? '--'} · α {primary.loraAlpha ?? '--'}</span></div>
                        <div className="flex justify-between gap-2"><span className="text-ink/45">Epochs</span><span className="text-ink-bright text-right">{primary.epochs ?? '--'} @ bs {primary.batchSize ?? '--'}</span></div>
                        <div className="flex justify-between gap-2"><span className="text-ink/45">Runtime</span><span className="text-ink-bright text-right">{primary.trainRuntime ? `${primary.trainRuntime.toFixed(1)}s` : '--'}</span></div>
                        <div className="flex justify-between gap-2"><span className="text-ink/45">W&B</span><span className="text-ink-bright text-right">{primary.wandbEnabled ? 'enabled' : 'disabled'}</span></div>
                        <div className="flex justify-between gap-2"><span className="text-ink/45">Link status</span><span className="text-ink-bright text-right">{linkedJob ? linkedJob.status : 'no job match'}</span></div>
                      </div>
                    </div>

                    <div className="rounded border border-line/60 bg-bg/20 p-3">
                      <div className="flex items-center justify-between mb-3">
                        <div className="text-[10px] uppercase tracking-widest text-ink/40">Quality gate</div>
                        <AlertTriangle className="w-3.5 h-3.5 text-warning" />
                      </div>
                      {primary.quality ? (
                        <div className="space-y-3">
                          <div className="flex items-end justify-between gap-2">
                            <div>
                              <div className="text-lg font-bold text-ink-bright">{Math.round(primary.quality.pass_rate * 100)}%</div>
                              <div className="text-[10px] text-ink/45">{qualityLabel(primary.quality)} · {primary.quality.passed}/{primary.quality.total} passed</div>
                            </div>
                            <div className="text-[10px] text-ink/45 text-right">
                              {primary.quality.categories ? Object.keys(primary.quality.categories).length : 0} categories
                            </div>
                          </div>
                          <div className="space-y-1 text-[10px]">
                            {Object.entries(primary.quality.categories || {}).slice(0, 4).map(([name, value]) => (
                              <div key={name} className="flex justify-between gap-2">
                                <span className="text-ink/45 capitalize">{name}</span>
                                <span className={cn((value.pass_rate ?? 0) >= 0.8 ? 'text-success' : (value.pass_rate ?? 0) >= 0.6 ? 'text-warning' : 'text-danger')}>
                                  {Math.round((value.pass_rate ?? 0) * 100)}%
                                </span>
                              </div>
                            ))}
                          </div>
                        </div>
                      ) : (
                        <div className="text-[11px] text-ink/45">Dataset quality summary not available for this technique.</div>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            )}
          </Card>

          <Card className="h-[17rem] overflow-hidden" title="Run Comparison" subtitle={`${compareCount} active`}> 
            {selectedRuns.length === 0 ? (
              <EmptyState title="No comparison target" subtitle="Select at least one run to compare training loss, runtime, and dataset quality." />
            ) : (
              <div className="overflow-auto custom-scrollbar h-full">
                <table className="w-full text-[11px] font-mono">
                  <thead className="sticky top-0 bg-header/90 backdrop-blur-sm text-ink/45 uppercase tracking-widest">
                    <tr>
                      <th className="p-2 text-left">Run</th>
                      <th className="p-2 text-left">Model / Dataset</th>
                      <th className="p-2 text-right">Final</th>
                      <th className="p-2 text-right">Best</th>
                      <th className="p-2 text-right">ΔLoss</th>
                      <th className="p-2 text-right">Runtime</th>
                      <th className="p-2 text-right">Gate</th>
                      <th className="p-2 text-right">Action</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-line/20">
                    {profiles.map((profile) => (
                      <tr key={profile.key} className={cn(profile.key === primary?.key && 'bg-accent/10')}>
                        <td className="p-2 align-top">
                          <div className="font-bold text-ink-bright">{profile.npcKey}</div>
                          <div className="text-ink/45 truncate max-w-40">{shortText(profile.runId)}</div>
                        </td>
                        <td className="p-2 align-top text-ink/60">
                          <div className="truncate max-w-56">{profile.shortModel}</div>
                          <div className="truncate max-w-56 text-ink/40">{profile.shortDataset}</div>
                        </td>
                        <td className="p-2 text-right text-ink-bright">{metric(profile.finalLoss)}</td>
                        <td className="p-2 text-right text-ink-bright">{metric(profile.bestLoss)}</td>
                        <td className={cn('p-2 text-right', profile.lossDelta !== null && profile.lossDelta < 0 ? 'text-success' : 'text-warning')}>
                          {metric(profile.lossDelta)}
                        </td>
                        <td className="p-2 text-right text-ink/70">{profile.trainRuntime ? `${profile.trainRuntime.toFixed(1)}s` : '--'}</td>
                        <td className="p-2 text-right">
                          <span className={cn('px-2 py-0.5 rounded border text-[9px] uppercase tracking-widest', profile.quality ? (profile.quality.pass_rate >= 0.8 ? 'border-success/30 text-success' : profile.quality.pass_rate >= 0.6 ? 'border-warning/30 text-warning' : 'border-danger/30 text-danger') : 'border-line text-ink/45')}>
                            {profile.quality ? qualityLabel(profile.quality) : 'N/A'}
                          </span>
                        </td>
                        <td className="p-2 text-right">
                          {profile.key === primaryRunId ? (
                            <span className="text-accent">Primary</span>
                          ) : (
                            <button className="text-accent underline" onClick={() => togglePrimary(profile.key)}>Focus</button>
                          )}
                          {' '}
                          <button className="ml-2 text-ink/45 underline" onClick={() => toggleCompareRun(profile.key)}>
                            {compareRunIds.includes(profile.key) ? 'Remove' : 'Compare'}
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </div>
      </div>
    </motion.div>
  );
};
